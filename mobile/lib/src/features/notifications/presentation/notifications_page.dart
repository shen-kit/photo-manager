import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/widgets/async_state_widget.dart';
import '../../jobs/application/operations_providers.dart';

class NotificationsPage extends ConsumerWidget {
  const NotificationsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('Notifications'),
      actions: [
        IconButton(
          onPressed: () async {
            await ref.read(operationsRepositoryProvider).markAllRead();
            ref.invalidate(notificationsProvider);
          },
          icon: const Icon(Icons.done_all),
        ),
        IconButton(
          onPressed: () async {
            await ref
                .read(operationsRepositoryProvider)
                .deleteAllNotifications();
            ref.invalidate(notificationsProvider);
          },
          icon: const Icon(Icons.delete_sweep),
        ),
      ],
    ),
    body: AsyncStateWidget(
      value: ref.watch(notificationsProvider),
      isEmpty: (items) => items.isEmpty,
      empty: const EmptyState(message: 'No notifications'),
      data: (items) => ListView.separated(
        itemCount: items.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) => ListTile(
          leading: Icon(
            items[index].isUnread
                ? Icons.notifications_active
                : Icons.notifications_none,
            color: items[index].isUnread ? Colors.amber : null,
          ),
          title: Text(items[index].title),
          subtitle: Text(
            [
              items[index].category,
              items[index].message,
            ].whereType<String>().join(' • '),
          ),
          trailing: IconButton(
            icon: const Icon(Icons.close),
            onPressed: () async {
              await ref
                  .read(operationsRepositoryProvider)
                  .deleteNotification(items[index].id);
              ref.invalidate(notificationsProvider);
            },
          ),
          onTap: () async {
            await ref
                .read(operationsRepositoryProvider)
                .markRead(items[index].id);
            ref.invalidate(notificationsProvider);
          },
        ),
      ),
    ),
  );
}
