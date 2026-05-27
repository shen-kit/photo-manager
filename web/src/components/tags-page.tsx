"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, LoaderCircle, Plus, RefreshCcw, Square, Tags, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetDetailModal } from "@/components/asset-detail-modal";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import { batchAddAssetTags, batchRemoveAssetTags, listAssets } from "@/lib/api/assets";
import { createTag, deleteTag, listTags, updateTag } from "@/lib/api/tags";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { AssetGridItem, Tag } from "@/lib/types";

const PAGE_SIZE = 24;

type TagFormState = {
  name: string;
  parentId: string;
  description: string;
  coverAssetId: string;
};

const emptyForm: TagFormState = { name: "", parentId: "", description: "", coverAssetId: "" };

function tagDepth(tag: Tag) {
  return tag.path.split(".").length - 1;
}

function tagLabel(tag: Tag) {
  return `${"— ".repeat(tagDepth(tag))}${tag.name} (${tag.path})`;
}

function assetTitle(asset: AssetGridItem) {
  return asset.id.slice(0, 8);
}

function placeholderStyle(seed: string) {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = seed.charCodeAt(index) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return { background: `linear-gradient(135deg, hsl(${hue} 65% 22%), hsl(${(hue + 48) % 360} 70% 32%))` };
}

export function TagsPage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } = useSessionBootstrap();
  const { pushToast } = useToast();
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [editTagId, setEditTagId] = useState<number | null>(null);
  const [form, setForm] = useState<TagFormState>(emptyForm);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [detailAssetId, setDetailAssetId] = useState<string | null>(null);

  const tagsQuery = useQuery({ queryKey: ["tags"], queryFn: listTags, enabled: accessReady });
  const assetsQuery = useQuery({
    queryKey: ["assets", "tags", selectedTagId],
    queryFn: () => listAssets({ limit: PAGE_SIZE, tagIds: selectedTagId ? [selectedTagId] : undefined }),
    enabled: accessReady,
  });

  const tags = useMemo(() => (tagsQuery.data ?? []).slice().sort((a, b) => a.path.localeCompare(b.path)), [tagsQuery.data]);
  const selectedTag = tags.find((tag) => tag.id === selectedTagId) ?? null;
  const editTag = tags.find((tag) => tag.id === editTagId) ?? null;
  const assets = assetsQuery.data?.items ?? [];
  const allVisibleSelected = assets.length > 0 && assets.every((asset) => selectedAssetIds.includes(asset.id));
  const assetNav = assets.map((asset) => ({ id: asset.id, mime_type: asset.mime_type }));

  const resetForm = () => {
    setEditTagId(null);
    setForm(emptyForm);
  };

  const saveTagMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim(),
        parent_id: form.parentId ? Number(form.parentId) : null,
        description: form.description.trim() || null,
        cover_asset_id: form.coverAssetId.trim() || null,
      };
      return editTagId ? updateTag(editTagId, payload) : createTag(payload);
    },
    onSuccess: async (tag) => {
      pushToast(editTagId ? "Tag updated" : "Tag created", "success");
      setSelectedTagId(tag.id);
      resetForm();
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const deleteTagMutation = useMutation({
    mutationFn: ({ tagId, deleteChildren }: { tagId: number; deleteChildren: boolean }) => deleteTag(tagId, deleteChildren),
    onSuccess: async (_, variables) => {
      pushToast("Tag deleted", "success");
      if (selectedTagId === variables.tagId) setSelectedTagId(null);
      if (editTagId === variables.tagId) resetForm();
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const batchAddMutation = useMutation({
    mutationFn: () => batchAddAssetTags(selectedAssetIds, selectedTagId ? [selectedTagId] : []),
    onSuccess: async (response) => {
      pushToast(`Added ${response.updated_count} tag assignment${response.updated_count === 1 ? "" : "s"}`, "success");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const batchRemoveMutation = useMutation({
    mutationFn: () => batchRemoveAssetTags(selectedAssetIds, selectedTagId ? [selectedTagId] : []),
    onSuccess: async (response) => {
      pushToast(`Removed ${response.updated_count} tag assignment${response.updated_count === 1 ? "" : "s"}`, "success");
      setSelectedAssetIds([]);
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const startEdit = (tag: Tag) => {
    const parent = tags.find((candidate) => candidate.path === tag.parent_path);
    setEditTagId(tag.id);
    setForm({
      name: tag.name,
      parentId: parent ? String(parent.id) : "",
      description: tag.description ?? "",
      coverAssetId: tag.cover_asset_id ?? "",
    });
  };

  const toggleAsset = (assetId: string) => {
    setSelectedAssetIds((current) => current.includes(assetId) ? current.filter((id) => id !== assetId) : [...current, assetId]);
  };

  if (isBootstrapping) {
    return <main className="flex min-h-screen items-center justify-center text-slate-300">Preparing tags...</main>;
  }

  if (!accessReady || !currentUser) {
    return <LoginScreen onLoggedIn={async () => { setAccessReady(true); await queryClient.invalidateQueries({ queryKey: ["auth", "me"] }); }} />;
  }

  return (
    <>
      <AppShell
        currentUser={currentUser}
        title="Tags"
        description="Development UI for hierarchical tag CRUD, filtering, cover validation, and batch assignment."
        headerActions={
          <button type="button" onClick={() => void Promise.all([tagsQuery.refetch(), assetsQuery.refetch()])} className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white">
            <RefreshCcw className="h-4 w-4" /> Refresh
          </button>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-300"><Tags className="h-4 w-4" /></div>
                <div><h2 className="text-sm font-semibold text-white">Tag tree</h2><p className="text-xs text-slate-400">Select tag to filter descendants.</p></div>
              </div>
              <button type="button" onClick={() => setSelectedTagId(null)} className={`mb-2 w-full rounded-2xl border px-3 py-2 text-left text-sm ${selectedTagId === null ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-200"}`}>All assets</button>
              <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                {tags.map((tag) => (
                  <div key={tag.id} className={`rounded-2xl border p-3 ${selectedTagId === tag.id ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/10 bg-white/5"}`}>
                    <button type="button" onClick={() => setSelectedTagId(tag.id)} className="w-full text-left text-sm text-white">{tagLabel(tag)}</button>
                    <div className="mt-2 flex gap-2 text-xs">
                      <button type="button" onClick={() => startEdit(tag)} className="rounded-full border border-white/10 px-2 py-1 text-slate-300">Edit</button>
                      <button type="button" onClick={() => deleteTagMutation.mutate({ tagId: tag.id, deleteChildren: false })} className="rounded-full border border-rose-400/30 px-2 py-1 text-rose-200">Delete leaf</button>
                      <button type="button" onClick={() => deleteTagMutation.mutate({ tagId: tag.id, deleteChildren: true })} className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-1 text-rose-200">Delete subtree</button>
                    </div>
                  </div>
                ))}
              </div>
              {tagsQuery.isError ? <p className="mt-3 text-xs text-rose-300">{tagsQuery.error.message}</p> : null}
            </section>

            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <h2 className="mb-3 text-sm font-semibold text-white">{editTag ? `Edit ${editTag.name}` : "Create tag"}</h2>
              <div className="space-y-3">
                <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Name" className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white" />
                <select value={form.parentId} onChange={(event) => setForm({ ...form, parentId: event.target.value })} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white">
                  <option value="">Root tag</option>
                  {tags.filter((tag) => tag.id !== editTagId).map((tag) => <option key={tag.id} value={tag.id}>{tagLabel(tag)}</option>)}
                </select>
                <input value={form.coverAssetId} onChange={(event) => setForm({ ...form, coverAssetId: event.target.value })} placeholder="Cover asset id (optional)" className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white" />
                <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Description" className="min-h-20 w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white" />
                <div className="flex gap-2">
                  <button type="button" onClick={() => saveTagMutation.mutate()} disabled={!form.name.trim() || saveTagMutation.isPending} className="flex flex-1 items-center justify-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200 disabled:opacity-60">
                    {saveTagMutation.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Save
                  </button>
                  <button type="button" onClick={resetForm} className="rounded-2xl border border-white/10 px-4 py-3 text-sm text-slate-200">Clear</button>
                </div>
              </div>
            </section>
          </aside>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-5 flex flex-col gap-3 border-b border-white/10 pb-4 md:flex-row md:items-center md:justify-between">
              <div><h2 className="text-lg font-semibold text-white">{selectedTag ? `Assets under ${selectedTag.path}` : "All assets"}</h2><p className="text-sm text-slate-400">{assets.length} shown · {selectedAssetIds.length} selected</p></div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setSelectedAssetIds(allVisibleSelected ? [] : assets.map((asset) => asset.id))} className="rounded-2xl border border-white/10 px-3 py-2 text-sm text-white">{allVisibleSelected ? "Clear page" : "Select page"}</button>
                <button type="button" onClick={() => batchAddMutation.mutate()} disabled={!selectedTagId || selectedAssetIds.length === 0 || batchAddMutation.isPending} className="rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200 disabled:opacity-60">Batch add selected tag</button>
                <button type="button" onClick={() => batchRemoveMutation.mutate()} disabled={!selectedTagId || selectedAssetIds.length === 0 || batchRemoveMutation.isPending} className="rounded-2xl border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-sm text-rose-200 disabled:opacity-60">Batch remove selected tag</button>
              </div>
            </div>
            {assetsQuery.isLoading ? <p className="text-sm text-slate-400"><LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />Loading assets...</p> : null}
            {assetsQuery.isError ? <p className="text-sm text-rose-300">{assetsQuery.error.message}</p> : null}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {assets.map((asset) => {
                const checked = selectedAssetIds.includes(asset.id);
                return (
                  <article key={asset.id} className="overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70">
                    <div className="relative aspect-square overflow-hidden">
                      <button type="button" onClick={() => toggleAsset(asset.id)} className="absolute left-3 top-3 z-10 rounded-full border border-white/20 bg-black/45 p-2 text-white">{checked ? <CheckSquare className="h-4 w-4 text-emerald-300" /> : <Square className="h-4 w-4" />}</button>
                      <button type="button" onClick={() => setDetailAssetId(asset.id)} className="block h-full w-full"><div className="absolute inset-0" style={placeholderStyle(asset.blurhash ?? asset.id)} /><img src={asset.small_thumbnail_url} alt={assetTitle(asset)} className="relative h-full w-full object-cover" /></button>
                    </div>
                    <div className="p-4 text-xs text-slate-300"><p className="font-semibold text-white">{assetTitle(asset)}</p><p>{asset.media_kind} · {asset.timeline_day}</p></div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      </AppShell>
      <AssetDetailModal assetId={detailAssetId} onClose={() => setDetailAssetId(null)} onSelectAsset={setDetailAssetId} navigationItems={assetNav} />
    </>
  );
}
