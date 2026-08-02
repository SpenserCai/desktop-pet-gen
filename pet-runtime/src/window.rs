//! Transparent, always-on-top, decoration-free overlay window — plus the
//! authoritative window-position anchor used for dragging.
//!
//! ## Why an explicit anchor
//!
//! Moving a borderless window requires writing [`Window::position`], which is
//! a [`WindowPosition::At`] in **physical** pixels
//! (`bevy_winit::winit_window_position` converts it to a
//! `PhysicalPosition<i32>`). A freshly created window however starts as
//! [`WindowPosition::Automatic`], so code that pattern-matches on
//! `WindowPosition::At(..)` never fires and the window appears "undraggable".
//!
//! [`WindowAnchor`] removes that failure mode:
//! * [`place_window`] runs until it succeeds and *deliberately* positions the
//!   window near the bottom-right of the primary monitor, recording the
//!   physical position;
//! * [`track_window_moved`] keeps the anchor in sync with reality by reading
//!   [`WindowMoved`] (the OS is authoritative and may clamp our request).
//!
//! Interaction systems then treat the anchor as the single source of truth and
//! only ever write `WindowPosition::At(anchor + delta_physical)`.

use bevy::prelude::*;
use bevy::window::{
    CompositeAlphaMode, Monitor, PrimaryMonitor, PrimaryWindow, WindowLevel, WindowMoved,
    WindowPosition,
};

use crate::config::{SPAWN_MARGIN_BOTTOM, SPAWN_MARGIN_RIGHT, WINDOW_SIZE};

/// System set containing the window-anchor bookkeeping.
///
/// Interaction systems that move the window must run *after* this set so they
/// observe the freshest OS-reported position.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct WindowAnchorSystems;

/// Build the [`WindowPlugin`] for a desktop-pet overlay window.
///
/// - [`WINDOW_SIZE`]² logical pixels — large enough for the action menu + HUD.
/// - Fully transparent background so only the sprite is visible.
/// - No OS decorations, not resizable, hidden from the taskbar / Dock.
/// - Always on top so the pet floats above other windows.
pub fn window_plugin() -> WindowPlugin {
    WindowPlugin {
        primary_window: Some(Window {
            title: "Desktop Pet".into(),
            transparent: true,
            decorations: false,
            window_level: WindowLevel::AlwaysOnTop,
            resizable: false,
            // `WindowResolution` is constructed from the *requested logical*
            // size (bevy_winit passes it to winit as a `LogicalSize`).
            resolution: (WINDOW_SIZE as u32, WINDOW_SIZE as u32).into(),
            // Prevent the window from appearing in the taskbar / dock.
            skip_taskbar: true,
            // Transparent windows require platform-specific alpha compositing
            // (official Bevy `transparent_window` example recipe).
            #[cfg(target_os = "macos")]
            composite_alpha_mode: CompositeAlphaMode::PostMultiplied,
            #[cfg(target_os = "linux")]
            composite_alpha_mode: CompositeAlphaMode::PreMultiplied,
            #[cfg(target_os = "windows")]
            composite_alpha_mode: CompositeAlphaMode::Auto,
            ..default()
        }),
        ..default()
    }
}

/// The window's current top-left position in **physical** pixels.
///
/// `None` until the window exists and either the OS reported a position or
/// [`place_window`] assigned one.
#[derive(Resource, Default, Debug)]
pub struct WindowAnchor {
    /// Physical top-left position of the window, if known.
    pub physical: Option<IVec2>,
    /// Whether the deliberate initial placement already happened.
    placed: bool,
}

impl WindowAnchor {
    /// Offset the anchor by a physical-pixel delta, returning the new value.
    ///
    /// Pure helper so the drag arithmetic is unit-testable without a `World`.
    pub fn offset(&mut self, delta_physical: IVec2) -> Option<IVec2> {
        let next = self.physical? + delta_physical;
        self.physical = Some(next);
        Some(next)
    }
}

/// Registers the window configuration side-effects (anchor bookkeeping).
pub struct PetWindowPlugin;

impl Plugin for PetWindowPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<WindowAnchor>().add_systems(
            Update,
            (place_window, track_window_moved)
                .chain()
                .in_set(WindowAnchorSystems),
        );
    }
}

/// Compute the deliberate initial window position (physical px): near the
/// bottom-right corner of the given monitor, inset by the spawn margins.
///
/// Pure function to keep the placement policy unit-testable.
pub fn initial_position(
    monitor_position: IVec2,
    monitor_size: UVec2,
    window_size_physical: UVec2,
    scale_factor: f32,
) -> IVec2 {
    let margin_x = (SPAWN_MARGIN_RIGHT * scale_factor) as i32;
    let margin_y = (SPAWN_MARGIN_BOTTOM * scale_factor) as i32;
    let x = monitor_position.x + monitor_size.x as i32 - window_size_physical.x as i32 - margin_x;
    let y = monitor_position.y + monitor_size.y as i32 - window_size_physical.y as i32 - margin_y;
    // Never place the window off the top-left of the monitor on tiny screens.
    IVec2::new(x.max(monitor_position.x), y.max(monitor_position.y))
}

/// Place the window once, then record the anchor.
///
/// Retries every frame until the primary monitor is known; falls back to
/// adopting an OS-provided `WindowPosition::At` when no monitor is reported.
fn place_window(
    mut anchor: ResMut<WindowAnchor>,
    mut windows: Query<&mut Window, With<PrimaryWindow>>,
    monitors: Query<&Monitor, With<PrimaryMonitor>>,
) {
    if anchor.placed {
        return;
    }
    let Ok(mut window) = windows.single_mut() else {
        return;
    };

    if let Ok(monitor) = monitors.single() {
        let scale = window.scale_factor().max(0.1);
        let target = initial_position(
            monitor.physical_position,
            monitor.physical_size(),
            UVec2::new(window.physical_width(), window.physical_height()),
            scale,
        );
        window.position = WindowPosition::At(target);
        anchor.physical = Some(target);
        anchor.placed = true;
        info!(
            "Window placed at {:?} (physical), scale_factor {:.2}",
            target, scale
        );
    } else if let WindowPosition::At(position) = window.position {
        // No monitor info (headless / exotic WM): adopt whatever the OS did.
        anchor.physical = Some(position);
        anchor.placed = true;
        warn!("No primary monitor reported; adopting OS position {position:?}");
    }
}

/// Keep [`WindowAnchor`] in sync with the OS-reported window position.
fn track_window_moved(mut moved: MessageReader<WindowMoved>, mut anchor: ResMut<WindowAnchor>) {
    for event in moved.read() {
        anchor.physical = Some(event.position);
        anchor.placed = true;
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_position_is_inset_from_bottom_right() {
        // 1920×1080 monitor at origin, 300×300 logical window, scale 1.
        let pos = initial_position(IVec2::ZERO, UVec2::new(1920, 1080), UVec2::splat(300), 1.0);
        assert_eq!(
            pos,
            IVec2::new(
                1920 - 300 - SPAWN_MARGIN_RIGHT as i32,
                1080 - 300 - SPAWN_MARGIN_BOTTOM as i32
            )
        );
    }

    #[test]
    fn initial_position_honours_scale_factor_and_monitor_offset() {
        // Secondary monitor to the right, 2× HiDPI: margins scale with it.
        let pos = initial_position(
            IVec2::new(1920, 0),
            UVec2::new(2880, 1800),
            UVec2::splat(600),
            2.0,
        );
        assert_eq!(
            pos,
            IVec2::new(
                1920 + 2880 - 600 - (SPAWN_MARGIN_RIGHT * 2.0) as i32,
                1800 - 600 - (SPAWN_MARGIN_BOTTOM * 2.0) as i32
            )
        );
    }

    #[test]
    fn initial_position_clamps_on_tiny_monitors() {
        let pos = initial_position(IVec2::ZERO, UVec2::new(320, 200), UVec2::splat(300), 1.0);
        assert_eq!(pos, IVec2::ZERO, "must never go off the monitor origin");
    }

    #[test]
    fn anchor_offset_requires_known_position() {
        let mut anchor = WindowAnchor::default();
        assert_eq!(anchor.offset(IVec2::new(5, 5)), None);

        anchor.physical = Some(IVec2::new(100, 200));
        assert_eq!(anchor.offset(IVec2::new(5, -7)), Some(IVec2::new(105, 193)));
        assert_eq!(anchor.physical, Some(IVec2::new(105, 193)));
    }
}
