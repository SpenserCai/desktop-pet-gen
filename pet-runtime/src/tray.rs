//! System-tray icon with a small menu (Show / Hide / Quit).
//!
//! Built on the `tray-icon` crate (which re-exports `muda` menu types under
//! `tray_icon::menu`). It is gated behind the `tray` cargo feature, which is
//! **off by default** so the core desktop-pet app always compiles — even on
//! platforms where tray support is problematic or the optional dependencies
//! are unavailable. Enable with:
//!
//! ```sh
//! cargo build --release --features tray
//! ```
//!
//! The tray icon image is generated procedurally at runtime (no asset files),
//! matching the warm "blob" branding of the fallback sprite.
//!
//! ## Threading note
//!
//! On macOS `TrayIcon` is `!Send` (it wraps `Rc`/`RefCell`), so it is stored
//! as a *non-send* resource and the tray must be created on the main thread.
//! We therefore build it during plugin setup (which runs on the main thread)
//! rather than from an ECS system, and pin the polling system to the main
//! thread by having it borrow the `NonSend<TrayIcon>`.

use bevy::prelude::*;

/// Plugin that wires up the system tray (no-op when the feature is disabled).
pub struct TrayPlugin;

impl Plugin for TrayPlugin {
    fn build(&self, app: &mut App) {
        #[cfg(feature = "tray")]
        imp::setup(app);

        #[cfg(not(feature = "tray"))]
        {
            let _ = app;
            println!("[tray] `tray` feature disabled; running without a system tray icon.");
        }
    }
}

// ---------------------------------------------------------------------------
// Real implementation (behind the `tray` feature)
// ---------------------------------------------------------------------------

#[cfg(feature = "tray")]
mod imp {
    use bevy::prelude::*;
    use tray_icon::menu::{Menu, MenuEvent, MenuId, MenuItem, PredefinedMenuItem};
    use tray_icon::{Icon, TrayIcon, TrayIconBuilder};

    /// Menu item identifiers we match incoming events against.
    #[derive(Resource)]
    struct MenuIds {
        show: MenuId,
        hide: MenuId,
        quit: MenuId,
    }

    /// Creates the tray icon + menu and registers the polling system.
    /// Runs on the main thread during app construction.
    pub fn setup(app: &mut App) {
        let menu = Menu::new();
        let show = MenuItem::new("Show", true, None);
        let hide = MenuItem::new("Hide", true, None);
        let separator = PredefinedMenuItem::separator();
        let quit = MenuItem::new("Quit", true, None);

        let _ = menu.append(&show);
        let _ = menu.append(&hide);
        let _ = menu.append(&separator);
        let _ = menu.append(&quit);

        let tray = TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip("Desktop Pet")
            .with_icon(make_icon())
            .build();

        match tray {
            Ok(tray) => {
                app.insert_resource(MenuIds {
                    show: show.id().clone(),
                    hide: hide.id().clone(),
                    quit: quit.id().clone(),
                });
                // `TrayIcon` is `!Send` on macOS → non-send resource. Keeping
                // it alive in the world keeps the tray icon visible.
                app.insert_non_send_resource(tray);
                app.add_systems(Update, poll_tray_events);
                println!("[tray] System tray icon initialized.");
            }
            Err(err) => {
                // Degrade gracefully: a missing tray must never crash the pet.
                println!("[tray] Failed to create tray icon: {err}");
            }
        }
    }

    /// Generates a simple 32×32 RGBA icon: a warm circular "blob" on a
    /// transparent background (echoes the fallback sprite branding).
    fn make_icon() -> Icon {
        const SIZE: u32 = 32;
        let center = SIZE as f32 / 2.0;
        let mut rgba = Vec::with_capacity((SIZE * SIZE * 4) as usize);
        for y in 0..SIZE {
            for x in 0..SIZE {
                let dx = x as f32 + 0.5 - center;
                let dy = y as f32 + 0.5 - center;
                let dist = (dx * dx + dy * dy).sqrt();
                if dist < center - 1.5 {
                    let t = dist / center; // 0 at center → 1 at edge
                    rgba.push(255); // R
                    rgba.push((255.0 * (0.55 + 0.35 * (1.0 - t))) as u8); // G
                    rgba.push(51); // B
                    rgba.push(255); // A
                } else {
                    rgba.extend_from_slice(&[0, 0, 0, 0]);
                }
            }
        }
        Icon::from_rgba(rgba, SIZE, SIZE).expect("procedural tray icon is valid")
    }

    /// Polls the global tray menu-event channel each frame.
    fn poll_tray_events(
        // Holding the `TrayIcon` (non-send) keeps it alive and pins this
        // system to the main thread, which macOS requires for tray operations.
        _tray: NonSend<TrayIcon>,
        ids: Res<MenuIds>,
        mut windows: Query<&mut Window>,
        mut commands: MessageWriter<crate::command::PetCommand>,
    ) {
        while let Ok(event) = MenuEvent::receiver().try_recv() {
            if event.id == ids.quit {
                // Route through the command bus so quitting behaves identically
                // no matter which surface requested it.
                commands.write(crate::command::PetCommand::Quit);
            } else if event.id == ids.show {
                if let Ok(mut window) = windows.single_mut() {
                    window.visible = true;
                }
            } else if event.id == ids.hide {
                if let Ok(mut window) = windows.single_mut() {
                    window.visible = false;
                }
            }
        }
    }
}
