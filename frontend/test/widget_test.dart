import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:recovery_ai/main.dart';

void main() {
  testWidgets('landing renders the CIMET masthead and the display heading',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 900));
    await tester.pumpWidget(const RecoveryAiApp());
    await tester.pump();

    // The handout's masthead and accent word.
    expect(find.text('CIMET.'), findsWidgets);
    expect(find.text('/ econnex'), findsOneWidget);
    // DisplayHeading is a RichText, so the finder has to look inside it.
    expect(find.textContaining('Recover the', findRichText: true), findsWidgets);
    expect(find.textContaining('Listen.', findRichText: true), findsWidgets);

    // Scenario entry points the demo depends on.
    expect(find.textContaining('HANDOFF SCENARIO'), findsWidgets);
    expect(find.textContaining('DNC BLOCK'), findsWidgets);
  });
}
