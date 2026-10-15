# Profiles

RetroManager starts with no profiles: there is one set of saves, favourites and play statuses, shared by everyone, and games are played with the saves RetroArch already keeps. That suits a console one person plays.

A **profile** is for a household where each person wants their own saves. It's a person's name, and a folder of that name inside the saves and save states folders:

```
saves/
├── snes/Game.srm              shared: nobody's in particular
├── alice/snes/Game.srm        Alice's
└── bob/snes/Game.srm          Bob's
savestates/
├── alice/snes/Game.state1
└── bob/...
```

With profiles, the browser player and the phone app ask (or know) whose save to use, the game details show each person's saves, and with login switched on each person has their own play statuses, want list, achievements and preferences too.

## Adding people

The profile button is at the right of the header (a plain 👤 while nobody is signed in). **Profiles and login** in its menu, or **🧰 Tools › Profiles and login**, lists the people and adds new ones. Adding a person makes their folders in `saves/` and `savestates/`.

If there are saves already, adding a person asks what becomes of them:

- **Keep them shared.** They stay where they are, for anyone to play with. The new person starts with none.
- **Move them to that person.** Every shared save and save state goes into the person's folders, under the same path it had (`saves/snes/Game.srm` becomes `saves/alice/snes/Game.srm`). What moved is listed in `moved-saves/` in RetroManager's data folder, should you need to put any back by hand.

Moving them only helps once RetroArch looks in the person's folder, which is the next part. Until it does, RetroArch on your console won't see the moved saves, so set that up first.

Login is separate, and optional: with it off, profiles only decide whose saves a game uses. See the README's "Profiles and login".

## Telling RetroArch about profiles

RetroArch has no notion of people. It has two settings, `savefile_directory` and `savestate_directory`, and writes every save into whatever folders they name. So "switching profile" on a console means changing those two settings to the person's folders.

### RetroPie and EmulationStation

[RetroPie profiles](https://github.com/DeltaGemini/retropie_profiles) (MIT, by DeltaGemini) does that from inside EmulationStation: it adds a **Profile Switcher** system whose "games" are the people. Choosing one rewrites the two settings in every system's `retroarch.cfg`. In short:

1. **Make the folders.** In the saves folder and the save states folder, one for each person. Adding the person in RetroManager makes them for you. Use exactly the same name everywhere, capitals included: RetroManager, the folders and the script must agree.

2. **Add the Profile Switcher system** to `es_systems.cfg`:

   ```xml
   <system>
       <name>profile_switcher</name>
       <fullname>Profile Switcher</fullname>
       <path>/opt/retropie/configs/all/emulationstation/scripts/profiles</path>
       <extension>.sh .SH</extension>
       <command>%ROM%</command>
       <platform>profile_switcher</platform>
       <theme>profile_switcher</theme>
   </system>
   ```

3. **Make that folder**, `/opt/retropie/configs/all/emulationstation/scripts/profiles`, and put a copy of the repository's `Guest.sh` in it for each person, named after them (`alice.sh`). In each copy, change the profile's name and the two folders to that person's:

   ```bash
   sed -i 's|^savefile_directory = .*|savefile_directory = "/home/pi/RetroPie/saves/alice"|' "$cfg"
   sed -i 's|^savestate_directory = .*|savestate_directory = "/home/pi/RetroPie/savestates/alice"|' "$cfg"
   ```

   The paths are where the console keeps its saves. They have to be the same folders RetroManager is given as its saves and save states folders (`SAVES_DIR` and `SAVESTATES_DIR`, or `saves/` and `savestates/` inside `RETRO_DIR`), whether that's one disk both can see or folders kept in step by something like Syncthing.

4. **Make each script runnable** (over SSH):

   ```bash
   chmod +x /opt/retropie/configs/all/emulationstation/scripts/profiles/*.sh
   ```

5. **Restart EmulationStation**, open **Profile Switcher** and choose a person. From then on RetroArch saves into their folders, until someone else is chosen.

The script also records who's chosen (`/home/pi/RetroPie/profiles/current_profile`) and copies their photo to `profiles/photos/current.png`, which a theme can show; the repository's README has the lines for that. Its author describes it as experimental, so keep a backup of your saves before the first switch.

To go back to shared saves, a copy of the script with the two folders set to `saves` and `savestates` themselves does it.

### RetroArch on its own

Without EmulationStation, set the two folders by hand in RetroArch: **Settings › Directory › Save Files** and **Save States**, to the person's folders. Changing person means changing them again, so this suits a device one person uses: a phone, a handheld.

### The phone app

The app doesn't need RetroArch on the phone changed. It carries saves between the phone's own RetroArch folders and the person's folders on the server. Whose they are is the signed-in person; with login off, **📱 This phone › Saves and save states** chooses: everyone's (the shared saves), one of the people, or nobody.

### Playing in the browser

The play page asks whose save to use before a game starts: everyone's (the shared saves) unless you choose a person, or the signed-in person with login on.

## What RetroManager expects

- A person's saves in `saves/<name>/` and save states in `savestates/<name>/`, either straight in there or sorted into folders by system or by core, as RetroArch can.
- Anything not inside a person's folder is shared.
- Names are up to 24 letters, digits, `-` or `_`. A person can't be called `shared` or `users`.
- `SAVE_PROFILES` in `.env` can name people to start with (`SAVE_PROFILES=alice,bob`); it's only read until people have been added or changed in the app, which remembers them itself.

## Saves beside the games

People can only have saves of their own where RetroArch keeps saves in folders of their own (`saves/` and `savestates/`). Where it keeps them beside the games, in the ROM folders (RetroPie's way; **Tools › Settings › Saves** says which), there is one set, shared by everyone: profiles still have their own favourites, play status and sign-in, but every save and save state is everyone's, and adding a person doesn't offer to move saves.
