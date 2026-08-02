//! Design tokens for the overlay UI.
//!
//! Single source of truth for colours, type scale and spacing so the menu, HUD
//! and toasts stay visually consistent and a re-skin touches one file.
//!
//! ## Hard constraint: ASCII-only text
//!
//! Bevy embeds `FiraMono-subset.ttf` as its default font, whose `cmap` covers
//! exactly `U+0020..U+007E` (95 code points). Any other code point — emoji,
//! `✕`, `•`, CJK — renders as a "tofu" box. All UI copy in this runtime is
//! therefore ASCII, and iconography is drawn from primitive UI nodes
//! ([`super::icons`]) instead of glyphs. See
//! `docs/standards/RUNTIME_UX.md` for the full rule.

use bevy::prelude::*;

// ---------------------------------------------------------------------------
// Type scale (logical px)
// ---------------------------------------------------------------------------

/// Font size for menu rows.
pub const FONT_MENU: f32 = 12.0;
/// Font size for HUD vitals.
pub const FONT_HUD: f32 = 10.0;
/// Font size for toast notifications.
pub const FONT_TOAST: f32 = 11.0;

// ---------------------------------------------------------------------------
// Surfaces
// ---------------------------------------------------------------------------

/// Menu / panel background.
pub const SURFACE: Color = Color::srgba(0.11, 0.12, 0.15, 0.94);
/// Menu row background (idle).
pub const ROW: Color = Color::srgba(0.18, 0.19, 0.23, 0.0);
/// Menu row background (hovered).
pub const ROW_HOVER: Color = Color::srgba(0.29, 0.32, 0.40, 0.95);
/// Menu row background (pressed).
pub const ROW_PRESSED: Color = Color::srgba(0.38, 0.42, 0.52, 0.98);
/// HUD background.
pub const HUD_SURFACE: Color = Color::srgba(0.05, 0.07, 0.12, 0.78);
/// Toast background.
pub const TOAST_SURFACE: Color = Color::srgba(0.08, 0.09, 0.13, 0.86);

// ---------------------------------------------------------------------------
// Text & accents
// ---------------------------------------------------------------------------

/// Primary text colour.
pub const TEXT: Color = Color::srgb(0.93, 0.94, 0.97);
/// Dimmed text colour (labels, units).
pub const TEXT_DIM: Color = Color::srgb(0.62, 0.65, 0.72);
/// Achievement highlight.
pub const ACCENT_GOLD: Color = Color::srgb(1.0, 0.82, 0.35);
/// Destructive accent (Quit).
pub const ACCENT_DANGER: Color = Color::srgb(0.95, 0.42, 0.42);

/// Healthy stat colour.
pub const STAT_GOOD: Color = Color::srgb(0.55, 0.9, 0.6);
/// Warning stat colour.
pub const STAT_WARN: Color = Color::srgb(1.0, 0.7, 0.3);
/// Critical stat colour.
pub const STAT_BAD: Color = Color::srgb(1.0, 0.4, 0.4);

// ---------------------------------------------------------------------------
// Spacing
// ---------------------------------------------------------------------------

/// Padding inside panels.
pub const PAD: f32 = 5.0;
/// Gap between menu rows.
pub const ROW_GAP: f32 = 2.0;
/// Corner radius for panels.
pub const RADIUS_PANEL: f32 = 7.0;
/// Corner radius for rows.
pub const RADIUS_ROW: f32 = 4.0;
/// Icon box side length.
pub const ICON_SIZE: f32 = 12.0;

/// Colour of a "good" stat (energy / happiness) at `value`.
pub fn good_stat_color(value: f32) -> Color {
    if value < 25.0 {
        STAT_BAD
    } else if value < 50.0 {
        STAT_WARN
    } else {
        STAT_GOOD
    }
}

/// Colour of the hunger stat at `value` (inverted: **high hunger is bad**).
pub fn hunger_color(value: f32) -> Color {
    if value > 75.0 {
        STAT_BAD
    } else if value > 50.0 {
        STAT_WARN
    } else {
        STAT_GOOD
    }
}

/// Convenience: a [`TextFont`] at `size` using the embedded default font.
pub fn font(size: f32) -> TextFont {
    TextFont {
        font_size: size,
        ..default()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stat_colors_switch_at_documented_thresholds() {
        assert_eq!(good_stat_color(10.0), STAT_BAD);
        assert_eq!(good_stat_color(30.0), STAT_WARN);
        assert_eq!(good_stat_color(80.0), STAT_GOOD);

        assert_eq!(hunger_color(90.0), STAT_BAD);
        assert_eq!(hunger_color(60.0), STAT_WARN);
        assert_eq!(hunger_color(10.0), STAT_GOOD);
    }
}
