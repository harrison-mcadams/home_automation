# Usenet arr stack on SpoonBox (Windows PC)

Why SpoonBox and not the Pi: SABnzbd's par2 repair and unpacking pin the CPU and disk for
minutes after every download. On the Pi that would delay puck's jobs and stutter Kodi.
The PC is always on, so it runs everything; the Pi only plays finished files over the network.

Native Windows installs (no Docker): lighter, fewer moving parts, NTFS hardlinks just work.

## What Harrison needs first
- A Usenet provider account (server host, port 563, username, password).
- At least one indexer account (API key), e.g. NZBGeek.
- Enough free disk space (1080p movie ~2-10 GB, TV season ~5-30 GB). An external drive can be added later.

## 1. Folders (downloads and library on the SAME drive, for instant hardlink moves)
```powershell
$D = "D:\data"   # or C:\data if there is only one drive
New-Item -ItemType Directory -Force "$D\usenet\incomplete","$D\usenet\complete\tv","$D\usenet\complete\movies","$D\media\tv","$D\media\movies"
```

## 2. Install (admin PowerShell; each prompts once for admin)
```powershell
winget install --id SABnzbdTeam.SABnzbd -e
winget install --id TeamSonarr.Sonarr -e
winget install --id TeamRadarr.Radarr -e
winget install --id TeamProwlarr.Prowlarr -e
```
(If an id isn't found, `winget search sonarr` etc., or use the installer from each project's site.)
In each installer, choose **"Install as Windows Service"** so it starts at boot with nobody logged in.
SABnzbd: Config > General > enable "Start SABnzbd as a Windows service" or add it to Startup.

Web UIs (via Tailscale):
- SABnzbd  http://spoonbox.tailcfee0c.ts.net:8080
- Prowlarr http://spoonbox.tailcfee0c.ts.net:9696
- Sonarr   http://spoonbox.tailcfee0c.ts.net:8989
- Radarr   http://spoonbox.tailcfee0c.ts.net:7878

## 3. Wire it together
1. **SABnzbd**: wizard with the provider details (SSL, port 563, connections per plan).
   Folders: temporary `D:\data\usenet\incomplete`, completed `D:\data\usenet\complete`.
   Categories: `tv` -> `tv`, `movies` -> `movies`. Copy the API key (Config > General).
   Config > Special: add `spoonbox.tailcfee0c.ts.net` to `host_whitelist`.
2. **Sonarr / Radarr**: Settings > Media Management > root folder `D:\data\media\tv` / `D:\data\media\movies`;
   "Use Hardlinks instead of Copy" on. Settings > Download Clients > SABnzbd, host `localhost`, port 8080,
   API key, category `tv` / `movies`. Copy each app's API key (Settings > General).
3. **Prowlarr**: Indexers > add the indexer. Settings > Apps > add Sonarr (`http://localhost:8989`) and
   Radarr (`http://localhost:7878`) with their API keys. Prowlarr pushes indexers into both.
4. Turn on authentication (Forms, username/password) in each app.
5. Windows Firewall: allow inbound 8080, 8989, 7878, 9696 on the Tailscale/private network only.

## 4. Play it on the Pi (Kodi)
Share `D:\data\media` read-only (folder Properties > Sharing > Advanced Sharing, Everyone: Read),
then in Kodi: Videos > Files > Add videos > `smb://spoonbox/media` (or the Tailscale name), and set
content to TV shows / Movies. Direct play over the network is light for the Pi; no transcoding.

## Optional later
- Jellyseerr (simple "request this" page). 5055 on SpoonBox is the Spirit Island TV page, so use 5056.
