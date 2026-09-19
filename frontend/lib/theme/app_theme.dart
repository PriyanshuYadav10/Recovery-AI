import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// CIMET / econnex design system - light theme.
///
/// Same brand accent as the handout (the one CIMET orange), rebuilt on a
/// light, plain-paper surface instead of the handout's own dark cover, so the
/// app reads as calm and easy to scan rather than as a technical dashboard.
/// Still two-tone on purpose: one accent colour, everything else is ink,
/// grey, or a rule - nothing competes with the accent for attention.
class AppTheme {
  // Surfaces
  static const bg = Color(0xFFFCFCFE);
  static const panel = Color(0xFFF6F7FB);
  static const panelAlt = Color(0xFFEDEEF6);

  // The one accent
  static const accent = Color(0xFFFF5B3D);

  // Type
  static const ink = Color(0xFF15161F);
  static const text = Color(0xFF23243A);
  static const body = Color(0xFF4B4C66);
  static const muted = Color(0xFF6C6D87);
  static const label = Color(0xFF80829B);
  static const faint = Color(0xFF9B9CB3);
  static const numeral = Color(0xFFAEAFC4);

  // Rules
  static const line = Color(0xFFE3E4EE);
  static const lineSoft = Color(0xFFD2D3E3);

  /// Semantic aliases. There is no second bright colour by design - the
  /// accent carries every "pay attention" moment, and everything else is a
  /// shade of ink, so status is never a colour quiz.
  static const alert = accent;
  static const warn = accent;
  static const danger = accent;
  static const accent2 = body;
  static const ok = text;

  /// A soft lift for panels/cards - used instead of a heavier border so
  /// surfaces read as raised paper rather than boxes with a line around them.
  static List<BoxShadow> cardShadow = [
    BoxShadow(color: ink.withValues(alpha: 0.05), blurRadius: 18, offset: const Offset(0, 6)),
  ];

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

  /// A quieter, plain-language label. Kept from the mono handout style only
  /// where a short tag genuinely helps (a status word); everywhere else uses
  /// plain sentence case now instead of tracked-out capitals.
  static TextStyle mono(
    double size, {
    Color color = label,
    double tracking = 0.4,
    FontWeight weight = FontWeight.w600,
  }) =>
      GoogleFonts.inter(
        fontSize: size,
        color: color,
        letterSpacing: tracking,
        fontWeight: weight,
      );

  static TextStyle figure(double size, {Color color = ink}) =>
      GoogleFonts.inter(
        fontSize: size,
        color: color,
        fontWeight: FontWeight.w700,
      );

  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: bg,
      canvasColor: bg,
      dividerColor: line,
      colorScheme: const ColorScheme.light(
        primary: accent,
        onPrimary: Colors.white,
        secondary: body,
        surface: panel,
        onSurface: text,
        error: accent,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme)
          .apply(bodyColor: body, displayColor: ink),
      appBarTheme: AppBarTheme(
        backgroundColor: bg,
        foregroundColor: ink,
        elevation: 0,
        titleTextStyle: heading(18),
      ),
      cardTheme: base.cardTheme.copyWith(
        color: panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: panel,
        hintStyle: prose(13).copyWith(color: faint),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: accent, width: 1.5),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: ink,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 14),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: text,
          side: const BorderSide(color: lineSoft),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: accent),
      ),
    );
  }
}
