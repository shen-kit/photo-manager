import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers.dart';
import '../../auth/application/auth_controller.dart';
import '../../backup/presentation/device_folders_page.dart';
import '../../jobs/presentation/jobs_page.dart';
import '../../notifications/presentation/notifications_page.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(authControllerProvider).valueOrNull;
    final settings = ref.watch(appSettingsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.person_outline),
            title: Text(session?.user.username ?? 'Not signed in'),
            subtitle: Text(settings.baseUrl),
          ),
          ListTile(
            leading: const Icon(Icons.folder_outlined),
            title: const Text('Backup folders'),
            subtitle: const Text('Choose device media folders/albums'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const DeviceFoldersPage()),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.work_outline),
            title: const Text('Jobs'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const JobsPage()),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.health_and_safety_outlined),
            title: const Text('System integrity'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const DiagnosticsPage()),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.notifications_outlined),
            title: const Text('Notifications'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const NotificationsPage()),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.cleaning_services_outlined),
            title: const Text('Clear local cache'),
            subtitle: const Text('Keeps account and selected settings'),
            onTap: () async {
              await settings.clearLocalCache();
              if (context.mounted)
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Local cache cleared')),
                );
            },
          ),
          const AboutListTile(
            icon: Icon(Icons.info_outline),
            applicationName: 'Photo Manager Mobile',
            applicationVersion: '0.1.0',
            applicationLegalese: 'Self-hosted photo manager mobile client.',
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Log out'),
            onTap: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
    );
  }
}
