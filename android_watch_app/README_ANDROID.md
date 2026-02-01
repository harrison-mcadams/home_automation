# ⌚️ PuckRemote: Your Custom Android Wear OS App

This guide will walk you through building your very first Android Wear OS app to control your Raspberry Pi.
We will use **Jetpack Compose for Wear OS**, which is the modern (and much easier) way to build watch apps.

## 🛠️ Prerequisites

1.  **Download Android Studio:** [developer.android.com/studio](https://developer.android.com/studio)
2.  **Your Raspberry Pi IP:** You need the IP address of your Pi (e.g., `192.168.1.50`).
3.  **Running Server:** Ensure `python rf_testing/rf_api.py` is running on the Pi.

## 🚀 Step 1: Create the Project

1.  Open Android Studio.
2.  **New Project** -> Select **Wear OS** in the left panel.
3.  Choose **Empty Wear App** (with the Compose logo).
4.  Name: `PuckRemote`
5.  Language: **Kotlin** (Java is dead for Android dev, trust me).
6.  Click **Finish**.

## 📦 Step 2: Add Dependencies

We need two libraries:
*   **Retrofit:** To make HTTP requests to your Flask API.
*   **Gson:** To convert JSON to objects.

Open `build.gradle.kts (Module: app)`:
Add these to the `dependencies { ... }` block:

```kotlin
// Networking
implementation("com.squareup.retrofit2:retrofit:2.9.0")
implementation("com.squareup.retrofit2:converter-gson:2.9.0")
```

Click **Sync Now** at the top right.

## 🔓 Step 3: Permissions

We need internet access.
Open `manifests/AndroidManifest.xml`:
Add this line *above* the `<application>` tag:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

Also, because your Pi is on a local network (HTTP, not HTTPS), we need to allow "Cleartext" traffic.
Inside the `<application ...>` tag, add:
```xml
android:usesCleartextTraffic="true"
```

## 🧠 Step 4: The Code

I have provided three files for you in this directory. You can copy-paste them into your project source folder (`app/src/main/java/com/example/puckremote/`).

1.  **`PuckApi.kt`**: Defines how we talk to your Pi.
2.  **`MainActivity.kt`**: The UI (The buttons).
3.  **`Theme.kt`**: (Optional) Makes it look consistent.

## 🏃 Step 5: Run It!

1.  Connect your Pixel Watch via Wireless Debugging (or use the Emulator).
2.  Press the Green "Play" button in Android Studio.
3.  Tap "ON". Watch the logs on your Pi! 
