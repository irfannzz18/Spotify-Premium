package com.snuffy.app

import android.annotation.SuppressLint
import android.database.Cursor
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.view.View
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Callable
import java.util.concurrent.FutureTask
import kotlin.math.max

class MainActivity : ComponentActivity() {

    private lateinit var web: WebView
    private lateinit var player: ExoPlayer
    private val main = Handler(Looper.getMainLooper())

    private var queue = JSONArray()
    private var index = -1
    private var shuffle = false
    private var repeat = false
    private var volume = 70
    private var state = "stopped"
    private var error = ""
    private var gen = 0

    private val filePicker = registerForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris: List<Uri> -> if (uris.isNotEmpty()) handlePicked(uris) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.BLACK),
            navigationBarStyle = SystemBarStyle.dark(Color.BLACK)
        )
        super.onCreate(savedInstanceState)

        window.decorView.setBackgroundColor(Color.BLACK)
        if (Build.VERSION.SDK_INT >= 28) {
            val attrs = window.attributes
            attrs.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            window.attributes = attrs
        }
        hideSystemBars()

        web = WebView(this).apply {
            setBackgroundColor(Color.BLACK)
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_NEVER
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = WebViewClient()
            addJavascriptInterface(Bridge(), "AndroidBridge")
            loadUrl("file:///android_asset/index.html")
        }
        setContentView(web)

        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        player = ExoPlayer.Builder(this).build()
        player.volume = volume / 100f
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) advance()
            }
            override fun onPlayerError(e: PlaybackException) {
                state = "error"
                error = "Playback failed"
            }
        })
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    private fun hideSystemBars() {
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        controller.hide(WindowInsetsCompat.Type.systemBars())
    }

    override fun onDestroy() {
        if (::player.isInitialized) player.release()
        super.onDestroy()
    }

    private fun str(o: JSONObject, k: String): String =
        if (o.isNull(k)) "" else o.optString(k)

    private fun onMain(block: () -> String): String {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        val task = FutureTask(Callable { block() })
        main.post(task)
        return task.get()
    }

    /* ---------- file picking: audio plays directly, .txt becomes a song list ---------- */
    private fun displayName(uri: Uri): String = try {
        contentResolver.query(uri, null, null, null, null)?.use { c: Cursor ->
            val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (c.moveToFirst() && i >= 0) c.getString(i) else null
        } ?: uri.lastPathSegment ?: "Track"
    } catch (e: Exception) {
        "Track"
    }

    private fun isText(uri: Uri): Boolean =
        contentResolver.getType(uri)?.startsWith("text/") == true ||
            displayName(uri).endsWith(".txt", ignoreCase = true)

    private fun handlePicked(uris: List<Uri>) {
        val texts = uris.filter { isText(it) }
        val audios = uris.filter { !isText(it) }
        if (audios.isNotEmpty()) {
            val arr = JSONArray()
            audios.forEach { arr.put(JSONObject().put("uri", it.toString()).put("title", displayName(it))) }
            web.evaluateJavascript("window.__localTracks && window.__localTracks($arr)", null)
        }
        if (texts.isNotEmpty()) readTextFile(texts[0])
    }

    private fun readTextFile(uri: Uri) {
        Thread {
            try {
                val lines = contentResolver.openInputStream(uri)
                    ?.bufferedReader()
                    ?.use { it.readLines() } ?: emptyList()
                val songs = lines.map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }
                main.post {
                    web.evaluateJavascript("window.__fileLines && window.__fileLines(${JSONArray(songs)})", null)
                }
            } catch (e: Exception) {
                // unreadable text file: ignored
            }
        }.start()
    }

    /* ---------- playback (main thread) ---------- */
    private fun applyQueue(arr: JSONArray, start: Int) {
        queue = arr
        playIndex(start)
    }

    private fun playIndex(i: Int) {
        val n = queue.length()
        if (n == 0) return
        index = ((i % n) + n) % n
        val item = queue.getJSONObject(index)
        val localUri = str(item, "uri")
        gen++
        val g = gen
        player.stop()
        state = "loading"
        error = ""

        if (localUri.isNotEmpty()) {
            startPlayback(localUri, JSONObject())
            return
        }

        val id = str(item, "id")
        val target = if (id.isNotEmpty())
            "https://www.youtube.com/watch?v=$id"
        else
            "ytsearch1:" + str(item, "title")

        Thread {
            try {
                val raw = Python.getInstance().getModule("ytresolve")
                    .callAttr("stream_url", target).toString()
                val info = JSONObject(raw)
                val url = info.getString("url")
                val headers = info.optJSONObject("headers") ?: JSONObject()
                main.post {
                    if (g != gen) return@post
                    startPlayback(url, headers)
                }
            } catch (e: Exception) {
                main.post {
                    if (g == gen) {
                        state = "error"
                        error = "Could not load this track"
                    }
                }
            }
        }.start()
    }

    private fun startPlayback(url: String, headers: JSONObject) {
        val props = HashMap<String, String>()
        val keys = headers.keys()
        while (keys.hasNext()) {
            val k = keys.next()
            props[k] = headers.optString(k)
        }
        val httpFactory = DefaultHttpDataSource.Factory()
            .setAllowCrossProtocolRedirects(true)
            .setDefaultRequestProperties(props)
        val source = DefaultMediaSourceFactory(DefaultDataSource.Factory(this, httpFactory))
            .createMediaSource(MediaItem.fromUri(url))
        player.setMediaSource(source)
        player.prepare()
        player.play()
        state = "playing"
    }

    private fun advance() {
        val n = queue.length()
        if (n == 0) return
        if (repeat) { playIndex(index); return }
        val next = if (shuffle && n > 1)
            (0 until n).filter { it != index }.random()
        else
            index + 1
        if (next >= n) { state = "stopped"; return }
        playIndex(next)
    }

    private fun control(action: String, value: String) {
        when (action) {
            "toggle" -> {
                if (state == "playing" && player.isPlaying) player.pause()
                else if (state == "playing") player.play()
                else if (queue.length() > 0) playIndex(max(index, 0))
            }
            "next" -> {
                val n = queue.length()
                if (n == 0) return
                playIndex(if (shuffle && n > 1) (0 until n).random() else index + 1)
            }
            "prev" -> {
                if (player.currentPosition > 3000) player.seekTo(0)
                else playIndex(index - 1)
            }
            "seek" -> player.seekTo(((value.toDoubleOrNull() ?: 0.0) * 1000).toLong())
            "volume" -> {
                volume = value.toIntOrNull() ?: volume
                player.volume = volume / 100f
            }
            "shuffle" -> shuffle = !shuffle
            "repeat" -> repeat = !repeat
            "stop" -> { gen++; player.stop(); state = "stopped" }
        }
    }

    private fun statusJson(): JSONObject {
        val o = JSONObject()
        val t = queue.optJSONObject(index)
        o.put("state", state)
        o.put("error", error)
        o.put("paused", state == "playing" && !player.isPlaying)
        o.put("shuffle", shuffle)
        o.put("repeat", repeat)
        o.put("volume", volume)
        o.put("index", index)
        o.put("position", player.currentPosition / 1000.0)
        o.put("duration", if (player.duration > 0) player.duration / 1000.0 else 0.0)
        if (t == null) {
            o.put("track", JSONObject.NULL)
        } else {
            o.put(
                "track",
                JSONObject()
                    .put("title", str(t, "title"))
                    .put("artist", str(t, "artist"))
                    .put("thumb", str(t, "thumb"))
            )
        }
        val q = JSONArray()
        for (i in 0 until queue.length()) {
            val item = queue.getJSONObject(i)
            q.put(JSONObject().put("title", str(item, "title")).put("artist", str(item, "artist")))
        }
        o.put("queue", q)
        return o
    }

    /* ---------- JavaScript bridge ---------- */
    inner class Bridge {

        @JavascriptInterface
        fun status(): String = onMain { this@MainActivity.statusJson().toString() }

        @JavascriptInterface
        fun control(action: String, value: String) {
            main.post { this@MainActivity.control(action, value) }
        }

        @JavascriptInterface
        fun setQueue(json: String, index: Int) {
            main.post { this@MainActivity.applyQueue(JSONArray(json), index) }
        }

        @JavascriptInterface
        fun pickFile() {
            main.post { filePicker.launch(arrayOf("*/*")) }
        }

        @JavascriptInterface
        fun search(q: String) {
            Thread {
                val json = try {
                    Python.getInstance().getModule("ytresolve")
                        .callAttr("search", q).toString()
                } catch (e: Exception) {
                    "[]"
                }
                main.post {
                    web.evaluateJavascript("window.__searchRes && window.__searchRes($json)", null)
                }
            }.start()
        }
    }
}
