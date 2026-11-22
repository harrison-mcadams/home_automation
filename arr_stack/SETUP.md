# Usenet arr stack on SpoonBox

Why SpoonBox and not the Pi: SABnzbd's par2 repair and unpacking pin the CPU and disk
for minutes after every download. On the Pi that would delay puck's jobs and stutter Kodi.
The Pi only plays finished files over the network.

## What you need first
- An external drive plugged into SpoonBox (downloads + library on the same drive).
- A Usenet provider account (server host, port 563, username, password).
- At least one indexer account (API key), e.g. NZBGeek.

## 1. Install Docker on SpoonBox
OrbStack is lighter than Docker Desktop on a Mac: `brew install --cask orbstack`, open it once,
and set it to start at login.

## 2. Make the folders
```bash
DATA=/Volumes/<YourDrive>/data
mkdir -p $DATA/usenet/incomplete $DATA/usenet/complete/{tv,movies} $DATA/media/{tv,movies}
```

## 3. Start the stack
```bash
cd ~/home_automation/arr_stack
cp .env.example .env   # set DATA_ROOT=/Volumes/<YourDrive>/data, PUID=$(id -u), PGID=$(id -g)
docker compose up -d
```

Web UIs (via Tailscale):
- SABnzbd  http://spoonbox.tailcfee0c.ts.net:8080
- Prowlarr http://spoonbox.tailcfee0c.ts.net:9696
- Sonarr   http://spoonbox.tailcfee0c.ts.net:8989
- Radarr   http://spoonbox.tailcfee0c.ts.net:7878

## 4. Wire it together
1. **SABnzbd**: run the wizard with your provider details (SSL, port 563, connections per your plan).
   Folders: temporary `/data/usenet/incomplete`, completed `/data/usenet/complete`.
   Categories: `tv` -> `tv`, `movies` -> `movies`. Copy the API key (Config > General).
   Config > Special: add `spoonbox.tailcfee0c.ts.net` to `host_whitelist`.
2. **Sonarr / Radarr**: Settings > Media Management > root folder `/data/media/tv` (Sonarr) or
   `/data/media/movies` (Radarr); turn on "Use Hardlinks instead of Copy".
   Settings > Download Clients > add SABnzbd, host `sabnzbd`, port 8080, API key, category `tv` / `movies`.
   Copy each app's API key (Settings > General).
3. **Prowlarr**: Indexers > add your indexer. Settings > Apps > add Sonarr (`http://sonarr:8989`)
   and Radarr (`http://radarr:7878`) with their API keys, Prowlarr server `http://prowlarr:9696`.
   Prowlarr then pushes indexers into both apps.
4. Set authentication (Forms + username/password) in each app when it asks.

## 5. Play it on the Pi (Kodi)
Share `/Volumes/<YourDrive>/data/media` from SpoonBox (System Settings > General > Sharing >
File Sharing), then in Kodi add it as an SMB video source and set content types (TV shows / Movies).
Direct play over the network is light for the Pi; no transcoding happens.
