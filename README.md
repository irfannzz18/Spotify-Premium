# Snuffy

A personal music player for Android. Play songs from YouTube, open audio files from your phone, make albums, and keep your liked songs.

## Features

- Search and play songs from YouTube (audio only)
- Open audio files from your phone (mp3, m4a, wav, flac, ogg, aac and more)
- Play `.txt` song lists, one song name per line
- Play, pause, next, previous, shuffle and repeat
- Draggable progress knob to move through a song
- Queue, liked songs and albums (create, open, play, shuffle, remove songs, delete)
- Dark and light theme
- Settings menu with Privacy Policy and Terms & Conditions
- Profile with name, date of birth (DD/MM/YYYY, or pick from calendar) and email, stored on your device

## Screens

- **Home:** player, search, results and queue
- **Albums:** create albums and add songs with the **+** button
- **Liked:** all songs you liked, with play all and shuffle
- **Menu (☰):** profile, settings, privacy policy, terms

## Build the APK on GitHub

1. Commit all project files to the `Snuffy` repo.
2. Go to **Actions → Build APK → Run workflow**.
3. When the run is green, download **Snuffy-APK** from Artifacts.
4. Extract the zip and install `Snuffy.apk-zip` on your Android phone.

## How it works

- **Interface:** `app/src/main/assets/index.html`, shown in an Android WebView
- **Playback:** ExoPlayer (Media3)
- **YouTube search and stream lookup:** yt-dlp, run inside the app with Chaquopy (embedded Python)
- **Local files:** opened with Android's file picker and played directly

## Notes

- Playback of YouTube songs needs an internet connection.
- Your albums, likes, queue, theme and profile are stored only on the device.
- Downloading YouTube videos is not included, because it breaks YouTube's terms.
- YouTube changes often. If search or playback stops working, update yt-dlp in `app/build.gradle.kts` and rebuild.

## Privacy and terms

- Privacy Policy and Terms & Conditions are available inside the app from the ☰ menu.
- This app is for personal use. Only play music you have the right to listen to.

## Developer

Made by **Irfan S**.
Project page: https://github.com/irfannzz18

© 2026 Snuffy™. All rights reserved.
