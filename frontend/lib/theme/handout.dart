import 'package:flutter/material.dart';
import 'app_theme.dart';

/// The handout's component vocabulary, rebuilt as widgets.
///
/// Numbered section labels, the orange-ruled callout, stat blocks, outline
/// chips, PRIMARY / GOOD TO HAVE badges, faded numeral cards and the running
/// footer. Screens compose these instead of hand-rolling decoration, which is
/// what keeps every surface on-brief.

/// A quiet numbered label above a heading, e.g. "01 - The domain".
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.number, this.title, {super.key, this.color = AppTheme.accent});

  final String number;
  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      '$number  ·  $title',
      style: AppTheme.mono(11, color: color, tracking: 0.4, weight: FontWeight.w700),
    );
  }
}

/// A small, quiet label used above panels and table headers.
class MonoLabel extends StatelessWidget {
  const MonoLabel(this.text, {super.key, this.color = AppTheme.label, this.size = 11});

  final String text;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) =>
      Text(text, style: AppTheme.mono(size, color: color, tracking: 0.2, weight: FontWeight.w600));
}

/// Big heading where one trailing word carries the accent, as with "listen."
class DisplayHeading extends StatelessWidget {
  const DisplayHeading(this.lead, {super.key, this.accentWord, this.size = 52});

  final String lead;
  final String? accentWord;
  final double size;

  @override
  Widget build(BuildContext context) {
    return RichText(
      text: TextSpan(
        style: AppTheme.display(size),
        children: [
          TextSpan(text: lead),
          if (accentWord != null)
            TextSpan(text: accentWord, style: AppTheme.display(size).copyWith(color: AppTheme.accent)),
        ],
      ),
    );
  }
}

/// Panel with the orange rule down its left edge - the handout's callout.
class Callout extends StatelessWidget {
  const Callout({super.key, required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: AppTheme.panel,
        border: Border(left: BorderSide(color: AppTheme.accent, width: 4)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          MonoLabel(label, color: AppTheme.accent),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}

/// A plain panel with a mono label and an optional right-hand marker.
class HandoutPanel extends StatelessWidget {
  const HandoutPanel({
    super.key,
    required this.label,
    required this.child,
    this.trailing,
    this.padding = const EdgeInsets.all(18),
  });

  final String label;
  final Widget child;
  final Widget? trailing;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppTheme.line),
      ),
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              MonoLabel(label),
              const Spacer(),
              if (trailing != null) trailing!,
            ],
          ),
          const SizedBox(height: 14),
          child,
        ],
      ),
    );
  }
}

/// `12 / HOURS` - large figure over a small mono caption.
class StatBlock extends StatelessWidget {
  const StatBlock(this.value, this.label, {super.key, this.color = AppTheme.ink, this.size = 30});

  final String value;
  final String label;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(value, style: AppTheme.figure(size, color: color)),
        const SizedBox(height: 6),
        MonoLabel(label, size: 9.5),
      ],
    );
  }
}

/// Outline chip, as used for the vertical names.
class HandoutChip extends StatelessWidget {
  const HandoutChip(this.text, {super.key, this.active = false});

  final String text;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: active ? AppTheme.accent : AppTheme.line),
        color: active ? AppTheme.accent.withValues(alpha: 0.10) : Colors.transparent,
      ),
      child: Text(
        text,
        style: AppTheme.prose(12.5).copyWith(color: active ? AppTheme.accent : AppTheme.muted),
      ),
    );
  }
}

/// Solid orange PRIMARY badge, or the muted GOOD TO HAVE variant.
class HandoutBadge extends StatelessWidget {
  const HandoutBadge(this.text, {super.key, this.primary = true});

  final String text;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
      decoration: BoxDecoration(
        color: primary ? AppTheme.accent : AppTheme.panelAlt,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        text,
        style: AppTheme.mono(11, color: primary ? AppTheme.ink : AppTheme.text,
            tracking: 0.2, weight: FontWeight.w700),
      ),
    );
  }
}

/// Faded numeral, bold title, muted body - the 01/02/03/04 step cards.
class NumberedCard extends StatelessWidget {
  const NumberedCard({
    super.key,
    required this.number,
    required this.title,
    required this.body,
    this.width = 190,
    this.dim = false,
  });

  final String number;
  final String title;
  final String body;
  final double width;
  final bool dim;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(number,
              style: AppTheme.figure(22, color: dim ? AppTheme.numeral : AppTheme.accent)),
          const SizedBox(height: 10),
          Text(title, style: AppTheme.heading(14)),
          const SizedBox(height: 6),
          Text(body, style: AppTheme.prose(12).copyWith(color: AppTheme.muted)),
        ],
      ),
    );
  }
}

/// Thin rule, matching the handout's section separators.
class HandoutRule extends StatelessWidget {
  const HandoutRule({super.key, this.top = 22, this.bottom = 22, this.color = AppTheme.line});

  final double top;
  final double bottom;
  final Color color;

  @override
  Widget build(BuildContext context) =>
      Padding(padding: EdgeInsets.only(top: top, bottom: bottom), child: Container(height: 1, color: color));
}

/// `CIMET HACKATHON - JAIPUR                                            02`
class HandoutFooter extends StatelessWidget {
  const HandoutFooter({super.key, this.left = 'CIMET HACKATHON - JAIPUR', this.right = ''});

  final String left;
  final String right;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const HandoutRule(top: 26, bottom: 12),
        Row(
          children: [
            MonoLabel(left, color: AppTheme.faint, size: 9.5),
            const Spacer(),
            MonoLabel(right, color: AppTheme.faint, size: 9.5),
          ],
        ),
      ],
    );
  }
}

/// The masthead: `CIMET. / econnex` with the live-brief marker opposite.
class Masthead extends StatelessWidget {
  const Masthead({super.key, required this.rightLabel, this.online = true});

  final String rightLabel;
  final bool online;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text('CIMET.', style: AppTheme.heading(15).copyWith(letterSpacing: -0.2)),
        const SizedBox(width: 6),
        Text('/ econnex', style: AppTheme.prose(14).copyWith(color: AppTheme.muted)),
        const Spacer(),
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            color: online ? AppTheme.accent : AppTheme.faint,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 10),
        MonoLabel(rightLabel, color: AppTheme.label, size: 9.5),
      ],
    );
  }
}

/// Waveform strip from the cover - bars driven by whatever value is passed.
class Waveform extends StatelessWidget {
  const Waveform({super.key, required this.levels, this.height = 54, this.barWidth = 9});

  final List<double> levels;
  final double height;
  final double barWidth;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final level in levels)
            Padding(
              padding: const EdgeInsets.only(right: 3),
              child: Container(
                width: barWidth,
                height: (height * level.clamp(0.12, 1.0)),
                color: AppTheme.accent,
              ),
            ),
        ],
      ),
    );
  }
}
