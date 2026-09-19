import 'package:flutter/material.dart';
import 'theme/app_theme.dart';
import 'screens/landing_screen.dart';
import 'screens/console_screen.dart';
import 'screens/inbox_screen.dart';
import 'screens/leads_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const RecoveryAiApp());
}

class RecoveryAiApp extends StatelessWidget {
  const RecoveryAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Recovery AI',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      initialRoute: '/',
      routes: {
        '/': (_) => const LandingScreen(),
        '/console': (_) => const ConsoleScreen(),
        '/inbox': (_) => const InboxScreen(),
        '/leads': (_) => const LeadsScreen(),
      },
    );
  }
}
