"use strict";

const $ = (id) => document.getElementById(id);

const audio = $("audio");

const state = {
  page: "home",
  results: [],
  liked: loadJSON("snuffy-liked", []),
  queue: loadJSON("snuffy-queue", []),
  currentIndex: -1,
  currentTrack: null,
  shuffle: false,
  repeat: false,
  searchTimer: null,
  searchRequest: 0
};

function loadJSON(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return Array.isArray(fallback) && !Array.isArray(value)
      ? fallback
      : value ?? fallback;
  } catch {
    return fallback;
  }
}

function saveJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn("Could not save browser data:", error);
  }
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function normaliseTrack(track) {
  return {
    id: String(track.id || ""),
    title: track.title || "Unknown title",
    artist: track.artist || "Unknown artist",
    thumbnail: track.thumbnail || "",
    duration: track.duration || 0,
    localUrl: track.localUrl || "",
    isLocal: Boolean(track.isLocal)
  };
}

/* ---------------------------
   Navigation
---------------------------- */

const pages = {
  home: "homePage",
  search: "searchPage",
  albums: "albumsPage",
  liked: "likedPage",
  queue: "queuePage",
  profile: "profilePage",
  settings: "settingsPage",
  privacy: "privacyPage",
  terms: "termsPage"
};

function showPage(name) {
  if (!pages[name]) return;

  state.page = name;

  Object.entries(pages).forEach(([page, id]) => {
    $(id).hidden = page !== name;
  });

  document.querySelectorAll("[data-page]").forEach(button => {
    button.classList.toggle(
      "active",
      button.dataset.page === name
    );
  });

  $("sidebar").classList.remove("open");

  if (name === "liked") renderLiked();
  if (name === "queue") renderQueue();
  if (name === "profile") renderProfile();
  if (name === "albums") renderAlbums();
}

document.querySelectorAll("[data-page]").forEach(button => {
  button.addEventListener("click", () => {
    showPage(button.dataset.page);
  });
});

$("menuButton").addEventListener("click", () => {
  $("sidebar").classList.toggle("open");
});

$("profileButton").addEventListener("click", () => {
  showPage("profile");
});

$("homeSearchButton").addEventListener("click", () => {
  showPage("search");
  $("searchInput").focus();
});

/* ---------------------------
   Search
---------------------------- */

async function searchSongs(query) {
  const cleanQuery = query.trim();
  const requestNumber = ++state.searchRequest;

  if (!cleanQuery) {
    state.results = [];
    $("searchResults").innerHTML = "";
    $("searchStatus").textContent = "";
    return;
  }

  showPage("search");
  $("searchStatus").textContent = "Searching...";
  $("searchResults").innerHTML = "";

  try {
    const response = await fetch(
      `/api/search?q=${encodeURIComponent(cleanQuery)}`,
      { headers: { "Accept": "application/json" } }
    );

    if (!response.ok) {
      throw new Error("Search request failed");
    }

    const data = await response.json();

    // Ignore older responses if the user typed a newer query.
    if (requestNumber !== state.searchRequest) return;

    state.results = (data.results || []).map(normaliseTrack);

    $("searchStatus").textContent = state.results.length
      ? `${state.results.length} results`
      : "No songs found. Try another search.";

    renderTrackList(
      $("searchResults"),
      state.results,
      "search"
    );
  } catch (error) {
    if (requestNumber !== state.searchRequest) return;

    state.results = [];
    $("searchStatus").textContent =
      "Search failed. Check your internet connection and try again.";
  }
}

$("searchInput").addEventListener("input", () => {
  const query = $("searchInput").value;
  $("clearSearch").style.display = query ? "block" : "none";

  clearTimeout(state.searchTimer);

  if (!query.trim()) {
    state.searchRequest++;
    $("searchStatus").textContent = "";
    $("searchResults").innerHTML = "";
    return;
  }

  state.searchTimer = setTimeout(() => {
    searchSongs(query);
  }, 350);
});

$("searchInput").addEventListener("keydown", event => {
  if (event.key === "Enter") {
    clearTimeout(state.searchTimer);
    searchSongs($("searchInput").value);
  }
});

$("clearSearch").addEventListener("click", () => {
  $("searchInput").value = "";
  $("clearSearch").style.display = "none";
  state.searchRequest++;
  $("searchResults").innerHTML = "";
  $("searchStatus").textContent = "";
  $("searchInput").focus();
});

/* ---------------------------
   Track lists
---------------------------- */

function renderTrackList(container, tracks, source) {
  if (!tracks.length) {
    container.innerHTML = `
      <div class="empty-panel">
        <div class="empty-icon">♫</div>
        <h3>No songs here</h3>
        <p>Search for music or import audio from your device.</p>
      </div>`;
    return;
  }

  container.innerHTML = tracks.map((track, index) => {
    const liked = state.liked.some(item =>
      item.id && item.id === track.id
    );

    const image = track.thumbnail
      ? `<img class="track-cover"
          src="${escapeHTML(track.thumbnail)}"
          alt=""
          loading="lazy"
          onerror="this.style.display='none'">`
      : `<div class="track-cover"></div>`;

    return `
      <div class="track-row">
        ${image}
        <div class="track-info">
          <strong>${escapeHTML(track.title)}</strong>
          <span>${escapeHTML(track.artist)}</span>
        </div>
        <button class="track-action ${liked ? "liked" : ""}"
          data-like="${index}" data-source="${source}"
          aria-label="Like song">${liked ? "♥" : "♡"}</button>
        <button class="play-track"
          data-play="${index}" data-source="${source}"
          aria-label="Play song">▶</button>
      </div>`;
  }).join("");

  container.querySelectorAll("[data-play]").forEach(button => {
    button.addEventListener("click", () => {
      const list = getList(button.dataset.source);
      const index = Number(button.dataset.play);
      playTrack(list[index], list, index);
    });
  });

  container.querySelectorAll("[data-like]").forEach(button => {
    button.addEventListener("click", () => {
      const list = getList(button.dataset.source);
      const index = Number(button.dataset.like);
      toggleLike(list[index]);
      renderTrackList(container, tracks, source);
    });
  });
}

function getList(source) {
  if (source === "search") return state.results;
  if (source === "liked") return state.liked;
  if (source === "queue") return state.queue;
  return [];
}

/* ---------------------------
   Playback
---------------------------- */

function getStreamUrl(track) {
  if (track.localUrl) return track.localUrl;
  if (!track.id) return "";
  return `/api/stream/${encodeURIComponent(track.id)}`;
}

async function playTrack(track, list = state.queue, index = 0) {
  if (!track) return;

  track = normaliseTrack(track);

  const streamUrl = getStreamUrl(track);

  if (!streamUrl) {
    alert("This song does not have a playable audio source.");
    return;
  }

  state.currentTrack = track;

  if (list && list.length) {
    state.queue = list.map(normaliseTrack);
    state.currentIndex = index;
    saveJSON("snuffy-queue", state.queue);
    renderQueue();
  } else {
    state.queue = [track];
    state.currentIndex = 0;
  }

  $("playerTitle").textContent = track.title;
  $("playerArtist").textContent = track.artist;
  $("playerCover").innerHTML = track.thumbnail
    ? `<img src="${escapeHTML(track.thumbnail)}" alt="">`
    : "♫";

  updatePlayerLike();

  audio.pause();
  audio.src = streamUrl;
  audio.load();

  try {
    await audio.play();
    $("playButton").textContent = "Ⅱ";
  } catch (error) {
    $("playButton").textContent = "▶";
    console.error("Playback error:", error);
    $("searchStatus").textContent =
      "Could not play this song. Try another result.";
  }
}

function playNext() {
  if (!state.queue.length) return;

  let nextIndex;

  if (state.shuffle && state.queue.length > 1) {
    do {
      nextIndex = Math.floor(Math.random() * state.queue.length);
    } while (nextIndex === state.currentIndex);
  } else {
    nextIndex = state.currentIndex + 1;
  }

  if (nextIndex >= state.queue.length) {
    if (state.repeat) {
      nextIndex = 0;
    } else {
      audio.pause();
      return;
    }
  }

  state.currentIndex = nextIndex;
  playTrack(state.queue[nextIndex], state.queue, nextIndex);
}

function playPrevious() {
  if (!state.queue.length) return;

  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }

  let previousIndex = state.currentIndex - 1;

  if (previousIndex < 0) {
    previousIndex = state.repeat
      ? state.queue.length - 1
      : 0;
  }

  state.currentIndex = previousIndex;
  playTrack(
    state.queue[previousIndex],
    state.queue,
    previousIndex
  );
}

$("playButton").addEventListener("click", async () => {
  if (!audio.src) {
    if (state.queue.length) {
      playTrack(
        state.queue[0],
        state.queue,
        0
      );
    }
    return;
  }

  if (audio.paused) {
    try {
      await audio.play();
    } catch (error) {
      console.error(error);
    }
  } else {
    audio.pause();
  }
});

$("nextButton").addEventListener("click", playNext);
$("previousButton").addEventListener("click", playPrevious);

$("shuffleButton").addEventListener("click", () => {
  state.shuffle = !state.shuffle;
  $("shuffleButton").classList.toggle("selected", state.shuffle);
});

$("repeatButton").addEventListener("click", () => {
  state.repeat = !state.repeat;
  $("repeatButton").classList.toggle("selected", state.repeat);
});

audio.addEventListener("play", () => {
  $("playButton").textContent = "Ⅱ";
});

audio.addEventListener("pause", () => {
  $("playButton").textContent = "▶";
});

audio.addEventListener("ended", () => {
  if (state.repeat && state.currentIndex >= 0) {
    audio.currentTime = 0;
    audio.play().catch(console.error);
  } else {
    playNext();
  }
});

audio.addEventListener("timeupdate", () => {
  if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;

  $("progress").value = Math.round(
    (audio.currentTime / audio.duration) * 1000
  );

  $("currentTime").textContent = formatTime(audio.currentTime);
  $("duration").textContent = formatTime(audio.duration);
});

audio.addEventListener("loadedmetadata", () => {
  $("duration").textContent = formatTime(audio.duration);
});

audio.addEventListener("error", () => {
  if (state.currentTrack) {
    console.warn("Audio could not be loaded.");
  }
});

$("progress").addEventListener("input", () => {
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    audio.currentTime =
      (Number($("progress").value) / 1000) * audio.duration;
  }
});

$("volume").addEventListener("input", () => {
  audio.volume = Number($("volume").value) / 100;
});

audio.volume = 0.8;

/* ---------------------------
   Likes
---------------------------- */

function toggleLike(track) {
  if (!track) return;

  const exists = state.liked.some(item =>
    (item.id && item.id === track.id) ||
    (item.localUrl && item.localUrl === track.localUrl)
  );

  if (exists) {
    state.liked = state.liked.filter(item =>
      !(
        (item.id && item.id === track.id) ||
        (item.localUrl && item.localUrl === track.localUrl)
      )
    );
  } else {
    state.liked.unshift(normaliseTrack(track));
  }

  saveJSON("snuffy-liked", state.liked);
  renderLiked();
  updatePlayerLike();
}

function updatePlayerLike() {
  const track = state.currentTrack;

  const liked = track && state.liked.some(item =>
    (item.id && item.id === track.id) ||
    (item.localUrl && item.localUrl === track.localUrl)
  );

  $("playerLike").textContent = liked ? "♥" : "♡";
  $("playerLike").classList.toggle("liked", Boolean(liked));
}

$("playerLike").addEventListener("click", () => {
  if (state.currentTrack) {
    toggleLike(state.currentTrack);
  }
});

function renderLiked() {
  $("likedCount").textContent =
    `${state.liked.length} songs`;

  renderTrackList(
    $("likedContent"),
    state.liked,
    "liked"
  );
}

/* ---------------------------
   Queue
---------------------------- */

function renderQueue() {
  $("queueCount").textContent =
    `${state.queue.length} songs`;

  renderTrackList(
    $("queueContent"),
    state.queue,
    "queue"
  );
}

/* ---------------------------
   Local file importing
---------------------------- */

function openFilePicker() {
  $("fileInput").click();
}

$("fileButton").addEventListener("click", openFilePicker);
$("settingsFileButton").addEventListener("click", openFilePicker);

$("fileInput").addEventListener("change", async event => {
  const files = Array.from(event.target.files || []);
  const audioFiles = files.filter(file =>
    file.type.startsWith("audio/") ||
    /\.(mp3|m4a|aac|ogg|wav|flac|opus|webm)$/i.test(file.name)
  );

  const textFiles = files.filter(file =>
    /\.txt$/i.test(file.name)
  );

  const localTracks = audioFiles.map(file => ({
    id: "",
    title: file.name.replace(/\.[^.]+$/, ""),
    artist: "On this device",
    thumbnail: "",
    localUrl: URL.createObjectURL(file),
    isLocal: true
  }));

  if (localTracks.length) {
    state.queue = localTracks;
    saveJSON("snuffy-queue", state.queue);
    renderQueue();
    await playTrack(localTracks[0], localTracks, 0);
    showPage("queue");
  }

  for (const file of textFiles) {
    try {
      const text = await file.text();
      const names = text
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(line => line && !line.startsWith("#"))
        .slice(0, 15);

      if (!names.length) continue;

      $("searchStatus").textContent =
        `Importing ${names.length} song names...`;

      const imported = [];

      for (const name of names) {
        const response = await fetch(
          `/api/search?q=${encodeURIComponent(name)}`
        );

        if (!response.ok) continue;

        const data = await response.json();

        if (data.results && data.results.length) {
          imported.push(normaliseTrack(data.results[0]));
        }
      }

      if (imported.length) {
        state.queue = imported;
        saveJSON("snuffy-queue", state.queue);
        renderQueue();
        await playTrack(imported[0], imported, 0);
        showPage("queue");
      }

      $("searchStatus").textContent =
        `Imported ${imported.length} matching songs.`;
    } catch (error) {
      console.error("Text import failed:", error);
      $("searchStatus").textContent =
        "Could not read that song list.";
    }
  }

  event.target.value = "";
});

/* ---------------------------
   Profile
---------------------------- */

function renderProfile() {
  const profile = loadJSON("snuffy-profile", {
    name: "Snuffy User"
  });

  $("displayName").value = profile.name || "Snuffy User";
  const first = (profile.name || "S").trim().charAt(0).toUpperCase() || "S";

  $("largeAvatar").textContent = first;
  $("profileButton").textContent = first;
}

$("saveProfile").addEventListener("click", () => {
  const name = $("displayName").value.trim() || "Snuffy User";

  saveJSON("snuffy-profile", { name });
  renderProfile();

  $("profileMessage").textContent = "Profile saved.";
});

/* ---------------------------
   Albums
---------------------------- */

function renderAlbums() {
  $("albumsContent").innerHTML = `
    <div class="empty-icon">▤</div>
    <h3>No albums yet</h3>
    <p>Album management can be added when the original APK album data and workflows are connected.</p>`;
}

/* ---------------------------
   Theme
---------------------------- */

function setTheme(theme) {
  const light = theme === "light";

  document.body.classList.toggle("light", light);
  $("themeSelect").value = light ? "light" : "dark";

  try {
    localStorage.setItem("snuffy-theme", light ? "light" : "dark");
  } catch {}
}

$("themeSelect").addEventListener("change", () => {
  setTheme($("themeSelect").value);
});

/* ---------------------------
   Startup
---------------------------- */

function startApp() {
  const savedTheme = localStorage.getItem("snuffy-theme") || "dark";
  setTheme(savedTheme);

  renderLiked();
  renderQueue();
  renderProfile();
  renderAlbums();
  updatePlayerLike();
}

startApp();
