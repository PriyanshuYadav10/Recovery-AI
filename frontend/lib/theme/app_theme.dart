import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// CIMET / econnex handout design system.
///
/// Every colour here was sampled from CIMET-Hackathon-Handout-v3.pdf, so the
/// console reads as part of the same brief rather than a generic dark theme.
/// The system is deliberately two-tone: deep indigo and a single orange. There
/// is no second bright accent - emphasis comes from weight and intensity, which
/// is what makes the handout look composed rather than busy.
class AppTheme {
  // Surfaces
  static const bg = Color(0xFF101124);
  static const panel = Color(0xFF181A3D);
  static const panelAlt = Color(0xFF22244A);

  // The one accent
  static const accent = Color(0xFFFF5B3D);

  // Type
  static const ink = Color(0xFFFFFFFF);
  static const text = Color(0xFFDCDCF2);
  static const body = Color(0xFFC3C5E0);
  static const muted = Color(0xFFA9ABCB);
  static const label = Color(0xFF8385AB);
  static const faint = Color(0xFF6A6C92);
  static const numeral = Color(0xFF5C5E82);

  // Rules
  static const line = Color(0xFF2B2D55);
  static const lineSoft = Color(0xFF35376A);

  /// Semantic aliases. The handout has no green or amber, so status is carried
  /// by intensity: orange demands attention, light text is neutral, faint
  /// recedes.
  static const alert = accent;
  static const warn = accent;
  static const danger = accent;
  static const accent2 = body;
  static const ok = text;

  /// Ranking and queue bands, strongest first.
  static Color band(String value) {
    switch (value.toLowerCase()) {
      case 'high':
        return accent;
      case 'medium':
        return text;
      default:
        return faint;
    }
  }

  // ---- type scale ---------------------------------------------------------

  static TextStyle display(double size) => GoogleFonts.inter(
        fontSize: size,
        height: 1.04,
        fontWeight: FontWeight.w700,
        color: ink,
        letterSpacing: -1.2,
      );

  static TextStyle heading(double size) => GoogleFonts.inter(
        fontSize: size,
        height: 1.15,
        fontWeight: FontWeight.w700,
        color: ink,
      );

  static TextStyle prose(double size) => GoogleFonts.inter(
        fontSize: size,
        height: 1.55,
        color: body,
      );

  /// The handout's signature: monospace, uppercase, very wide tracking.
  static TextStyle mono(
    double size, {
    Color color = label,
    double tracking = 2.6,
    FontWeight weight = FontWeight.w500,
  }) =>
      GoogleFonts.jetBrainsMono(
        fontSize: size,
        color: color,
        letterSpacing: tracking,
        fontWeight: weight,
      );

  static TextStyle figure(double size, {Color color = ink}) =>
      GoogleFonts.jetBrainsMono(
        fontSize: size,
        color: color,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.5,
      );

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: bg,
      canvasColor: bg,
      dividerColor: line,
      colorScheme: const ColorScheme.dark(
        primary: accent,
        onPrimary: bg,
        secondary: body,
        surface: panel,
        onSurface: text,
        error: accent,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme)
          .apply(bodyColor: body, displayColor: ink),
      appBarTheme: AppBarTheme(
        backgroundColor: bg,
        elevation: 0,
        titleTextStyle: heading(18),
      ),
      cardTheme: base.cardTheme.copyWith(
        color: panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(6),
          side: const BorderSide(color: line),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: panel,
        hintStyle: prose(13).copyWith(color: faint),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: accent),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: bg,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 13),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: text,
          side: const BorderSide(color: lineSoft),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: accent),
      ),
    );
  }
}
