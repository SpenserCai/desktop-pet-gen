//! Overlay UI: the action menu, the status HUD and toast notifications.
//!
//! The UI is split into a design-token module ([`theme`]), a font-free icon
//! system ([`icons`]) and one module per surface, so a new surface is a new
//! module plus one line in [`PetUiPlugin`].
//!
//! Two conventions keep the overlay honest:
//!
//! * **ASCII-only copy** — Bevy's embedded font covers `U+0020..U+007E`; see
//!   [`theme`] and `docs/standards/RUNTIME_UX.md`.
//! * **[`UiBlocker`] on interactive surfaces** — the pointer layer consults
//!   these regions so a click on the menu or HUD never reaches the pet.

pub mod hud;
pub mod icons;
pub mod menu;
pub mod theme;
pub mod toast;

use bevy::prelude::*;

pub use menu::{MenuRoot, MenuState};

/// Phases of the UI within a frame.
///
/// [`Input`](PetUiSystems::Input) runs before the command bus (so a menu click
/// takes effect the same frame), [`Present`](PetUiSystems::Present) runs after
/// the world settled (so the HUD and toasts show the freshest state).
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub enum PetUiSystems {
    /// Menu placement and row activation.
    Input,
    /// HUD refresh and toast lifetime.
    Present,
}

/// Marks a UI region that must absorb pointer input.
///
/// The pointer layer ([`crate::interaction`]) never starts a drag or pets the
/// sprite when the press lands inside a blocker.
#[derive(Component)]
pub struct UiBlocker;

/// Registers every UI surface.
pub struct PetUiPlugin;

impl Plugin for PetUiPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((menu::MenuPlugin, hud::HudPlugin, toast::ToastPlugin));
    }
}
