# Project1991 integration record

This directory is a maintained source snapshot of the MIT-licensed OpenCivOne
project. It is the authoritative Classic gameplay runtime for Project1991,
not merely a visual reference.

## Upstream pin

- Repository: <https://codeberg.org/rhorvat/OpenCivOne>
- Commit: `2f95a055a8d65957cbe54c24c132acc1ebd6acea`
- Commit date: 2026-07-24
- Commit subject: `Fix for issues #49 and #50`
- OpenCivOne package version: `1.475.6.7`

The upstream screenshot gallery under `src/Resources/Screenshots` is omitted.
It is documentation-only and is not needed to build or run the game.

## Project1991 integration patches

The following narrow patches are maintained on top of the pinned snapshot:

1. Correct `oParent` to `parent` in the Release intro drawing path.
2. Correct `oGameException` to `gameException` in the Release exception path.
3. Import `System.Reflection` for the Release resource-path code.
4. Allow `PROJECT1991_CIV1_PATH` to point at a legal local DOS Civilization
   directory, use it for read-only OpenCivOne and Virtual CPU resource
   operations, and route known mutable files through separate save paths.
5. Isolate the upstream project from Project1991's stricter analyzer policy.
   No analyzer cleanup is mixed into the imported gameplay code.
6. Replace the direct `Window` dependency in `OpenCivOneGame` with the
   platform-neutral `IClassicGameHost` dialog boundary and keep the Avalonia
   implementation in the shared `ClassicDialogPresenter`.
7. Add a German-first native shell text catalog for dialogs outside the
   original 320x200 framebuffer.
8. Extract the indexed-screen composition into the platform-neutral
   `ClassicFrameComposer`; keep the Avalonia desktop window as a thin
   framebuffer adapter.
9. Extract the original 320x200 pointer-coordinate translation and mouse-event
   coalescing into the platform-neutral `ClassicPointerInput`.
10. Extract the existing DOS key-code table and diagnostic key actions into
    the platform-neutral `ClassicKeyTranslator`; retain only physical Avalonia
    key-name translation in the desktop window.
11. Move runtime thread ownership, start/stop signaling, completion, and
    failure state into the platform-neutral `ClassicRuntimeSession`.
12. Add `ClassicGameSurface` as the single platform-neutral host boundary for
    frame capture, pointer input, DOS key input, pause state, and runtime
    lifecycle; make the desktop window consume this boundary.
13. Split the imported source into `OpenCivOne.Runtime.csproj` and the
    desktop-only `OpenCivOne.csproj`. Move the mouse event model into the
    runtime input folder and route the remaining runtime error messages
    through `IClassicGameHost`.
14. Move both projects to .NET 10 and Avalonia 12.1, give projects sharing the
    source directory separate intermediate build state, and keep the runtime
    free of `Avalonia.Desktop`.
15. Add `Project1991.Classic.Avalonia` as the shared Desktop/iPad frame,
    keyboard, pointer, touch, dialog, and integer-pixel presentation host.
16. Compose OpenCivOne's indexed cursor, palette, transparency, hotspot, and
    clipping into the fresh platform-neutral frame; hide the system cursor
    over that frame.
17. Add a thin official-template-style `net10.0-ios` Avalonia 12 starter with
    Scene/Activity and Single-View lifecycle support, without a custom
    `SceneDelegate`.
18. Introduce immutable `ClassicRuntimeOptions` and a guarded file resolver
    that separate read-only original resources from saves and logs.
19. Add a name-only Classic data manifest and platform-neutral import metadata
    validator for required files, traversal, invalid paths, and
    case-insensitive collisions.
20. Add the German-first iPad bootstrap and one-time folder import. Copy into
    a staging directory, revalidate and flush the copied data, journal the
    directory swap, recover interrupted imports, replace only resources, and
    preserve saves and logs.
21. Route legacy DOS file operations through instance-specific runtime paths.
    Treat `.SVE` and `.MAP` as one source/commit pair and seed `FAME.DTA`
    once into the writable save directory before read/write access. Pair
    commits use a cross-process slot lock, durable journal, backups, and
    repeatable recovery before every read or write.
22. Bind the iOS host to Avalonia's activatable lifetime, pause only while the
    app is backgrounded, keep player pauses intact, and make touch controls
    responsive down to compact iPad window widths.

Items 1-3 are compile repairs only. Item 4 changes resource discovery only.
Items 6-7 change only platform dialogs and their text. Item 8 preserves the
existing palette conversion and row-major framebuffer ordering while making
the composed frame reusable by the shared iPad host. Item 9 preserves the
original input queue behavior while allowing a scaled host surface to map
back to 320x200 coordinates. Item 10 preserves the exact keyboard codes and
modifier priority from the imported desktop handler. Item 11 moves existing
thread and exception handling out of the desktop window without changing the
game entry point or exit signal. Item 12 composes the preceding adapters into
one host API and preserves the original 1x1, 2x1, and 2x2 visible-screen
layouts. Item 13 changes project ownership and host routing only; the runtime
assembly no longer references `Avalonia.Desktop`. Items 14-17 replace platform
plumbing and presentation without replacing a game screen or rule. Items
18-22 protect user-supplied resources, validate import metadata, and keep
mutable legacy files outside the imported resources; the binary save format
is unchanged. None of these patches changes game rules, map generation, unit
behavior, city behavior, or save data.

## Update procedure

Before updating the pin:

1. compare the new upstream tree against this snapshot;
2. reapply or retire every documented integration patch explicitly;
3. build both Debug and Release;
4. launch with a complete legal DOS data directory;
5. verify intro, main menu, new game, one unit move, city founding, city view,
   save, and load;
6. record the new commit here and in `THIRD_PARTY_NOTICES.md`.

Do not replace this snapshot with an unpinned download.
