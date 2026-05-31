import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/widgets/async_state_widget.dart';
import '../application/operations_providers.dart';

class JobsPage extends ConsumerWidget {
  const JobsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('Jobs'),
      actions: [
        IconButton(
          onPressed: () => ref.invalidate(jobsProvider),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(jobsProvider);
        ref.invalidate(manualJobsProvider);
      },
      child: ListView(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Manual jobs',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          AsyncStateWidget(
            value: ref.watch(manualJobsProvider),
            data: (jobs) => Column(
              children: jobs
                  .map(
                    (job) => ListTile(
                      title: Text(job.title),
                      subtitle: Text(job.description),
                      trailing: FilledButton(
                        onPressed: job.isActive
                            ? null
                            : () async {
                                await ref
                                    .read(operationsRepositoryProvider)
                                    .runJob(job.jobKey, job.defaultParams);
                                ref.invalidate(jobsProvider);
                                ref.invalidate(manualJobsProvider);
                              },
                        child: Text(job.isActive ? 'Running' : 'Run'),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Recent jobs',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          AsyncStateWidget(
            value: ref.watch(jobsProvider),
            data: (jobs) => Column(
              children: jobs
                  .map(
                    (job) => ListTile(
                      leading: Icon(
                        job.isActive
                            ? Icons.timelapse
                            : job.status == 'failed'
                            ? Icons.error_outline
                            : Icons.check_circle_outline,
                      ),
                      title: Text(job.type),
                      subtitle: Text(
                        [
                          job.status,
                          job.progressMessage,
                          job.errorMessage,
                        ].whereType<String>().join(' • '),
                      ),
                      trailing: job.progressTotal == null
                          ? Text('${job.progressCurrent}')
                          : Text('${job.progressCurrent}/${job.progressTotal}'),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ),
    ),
  );
}

class DiagnosticsPage extends ConsumerWidget {
  const DiagnosticsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('System integrity')),
    body: AsyncStateWidget(
      value: ref.watch(diagnosticsProvider),
      data: (items) => ListView.separated(
        itemCount: items.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) => ListTile(
          title: Text(items[index].title),
          subtitle: Text(
            '${items[index].latestHealthState ?? 'not checked'} • ${items[index].description}',
          ),
          trailing: FilledButton.tonal(
            onPressed: () async {
              await ref
                  .read(operationsRepositoryProvider)
                  .runDiagnostic(items[index].key);
              ref.invalidate(diagnosticsProvider);
            },
            child: const Text('Run'),
          ),
        ),
      ),
    ),
  );
}
