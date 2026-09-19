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
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: const BorderRadius.horizontal(right: Radius.circular(14)),
        border: const Border(left: BorderSide(color: AppTheme.accent, width: 4)),
        boxShadow: AppTheme.cardShadow,
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
        borderRadius: BorderRadius.circular(14),
        boxShadow: AppTheme.cardShadow,
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
///
/// When [value] is a plain integer, it counts up from zero on first build
/// instead of just appearing - a small nudge that these are live numbers,
/// not printed copy.
class StatBlock extends StatelessWidget {
  const StatBlock(this.value, this.label, {super.key, this.color = AppTheme.ink, this.size = 30});

  final String value;
  final String label;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final target = int.tryParse(value);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (target == null)
          Text(value, style: AppTheme.figure(size, color: color))
        else
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: target.toDouble()),
            duration: const Duration(milliseconds: 900),
            curve: Curves.easeOutCubic,
            builder: (context, v, _) =>
                Text('${v.round()}', style: AppTheme.figure(size, color: color)),
          ),
        const SizedBox(height: 6),
        MonoLabel(label, size: 9.5),
      ],
    );
  }
}

/// Fades and lifts a child into place once, on first build - used once per
/// screen for the hero block so the page feels like it opens rather than
/// just appears.
class FadeSlideIn extends StatefulWidget {
  const FadeSlideIn({super.key, required this.child, this.delay = Duration.zero});

  final Widget child;
  final Duration delay;

  @override
  State<FadeSlideIn> createState() => _FadeSlideInState();
}

class _FadeSlideInState extends State<FadeSlideIn> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 520));
    Future.delayed(widget.delay, () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curved = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
    return AnimatedBuilder(
      animation: curved,
      builder: (context, child) => Opacity(
        opacity: curved.value,
        child: Transform.translate(offset: Offset(0, (1 - curved.value) * 14), child: child),
      ),
      child: widget.child,
    );
  }
}

/// Lifts a child a couple of pixels and adds a soft shadow under the pointer
/// - the one hover cue this web app uses, applied to every button and card.
class HoverLift extends StatefulWidget {
  const HoverLift({super.key, required this.child, this.lift = 3, this.borderRadius = 10});

  final Widget child;
  final double lift;
  final double borderRadius;

  @override
  State<HoverLift> createState() => _HoverLiftState();
}

class _HoverLiftState extends State<HoverLift> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      cursor: SystemMouseCursors.click,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 140),
        curve: Curves.easeOut,
        transform: Matrix4.translationValues(0, _hover ? -widget.lift : 0, 0),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.borderRadius),
          boxShadow: _hover
              ? [BoxShadow(color: AppTheme.ink.withValues(alpha: 0.10), blurRadius: 16, offset: const Offset(0, 8))]
              : const [],
        ),
        child: widget.child,
      ),
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
        if (online) const _PulseDot() else Container(
          width: 7,
          height: 7,
          decoration: const BoxDecoration(color: AppTheme.faint, shape: BoxShape.circle),
        ),
        const SizedBox(width: 10),
        MonoLabel(rightLabel, color: AppTheme.label, size: 9.5),
      ],
    );
  }
}

/// A small dot with a soft halo that expands and fades - "this is live."
class _PulseDot extends StatefulWidget {
  const _PulseDot();

  @override
  State<_PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<_PulseDot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 2))
      ..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value;
        return SizedBox(
          width: 16,
          height: 16,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 7 + t * 9,
                height: 7 + t * 9,
                decoration: BoxDecoration(
                  color: AppTheme.accent.withValues(alpha: (1 - t) * 0.35),
                  shape: BoxShape.circle,
                ),
              ),
              Container(
                width: 7,
                height: 7,
                decoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// A waveform that actually listens, instead of a printed graphic of one.
///
/// Each bar breathes on its own phase and speed, seeded from [levels] so real
/// activity (more calls, more handoffs) still shapes the pattern - it just
/// never sits still, the way audio never does. This is the one animated
/// flourish on the page, used exactly once, because the brief is "teach the
/// phone to listen": a static bar chart about listening undercuts its own
/// point.
class Waveform extends StatefulWidget {
  const Waveform({super.key, required this.levels, this.height = 54, this.barWidth = 9});

  final List<double> levels;
  final double height;
  final double barWidth;

  @override
  State<Waveform> createState() => _WaveformState();
}

class _WaveformState extends State<Waveform> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final List<double> _phase;
  late final List<double> _speed;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 60))
      ..repeat();
    // Deterministic per-bar phase/speed from each level, so a rebuild (a
    // metrics refresh) doesn't reset every bar to the same starting beat.
    _phase = [for (final l in widget.levels) (l * 137) % (2 * 3.14159)];
    _speed = [for (final l in widget.levels) 0.6 + (l * 53) % 1.0];
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final t = _controller.value * 2 * 3.14159 * 20; // slow, continuous
          return Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (var i = 0; i < widget.levels.length; i++)
                Padding(
                  padding: const EdgeInsets.only(right: 3),
                  child: Container(
                    width: widget.barWidth,
                    height: widget.height *
                        _breathe(widget.levels[i], _phase[i], _speed[i], t).clamp(0.10, 1.0),
                    decoration: BoxDecoration(
                      color: AppTheme.accent,
                      borderRadius: BorderRadius.circular(widget.barWidth / 2),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  double _breathe(double base, double phase, double speed, double t) {
    final wobble = 0.22 * (0.5 + 0.5 * _sin(t * speed + phase));
    return base + wobble - 0.11;
  }

  // A tiny sine approximation so this file needs no extra import for dart:math.
  double _sin(double x) {
    x = x % (2 * 3.14159);
    if (x < 0) x += 2 * 3.14159;
    final term = x < 3.14159 ? x : x - 2 * 3.14159;
    return term - (term * term * term) / 6 + (term * term * term * term * term) / 120;
  }
}
