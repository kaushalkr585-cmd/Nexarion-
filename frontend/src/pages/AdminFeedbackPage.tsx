import React, { useEffect, useState, useCallback } from "react";
import {
  CloseIcon,
  CopyIcon,
  EyeIcon,
  FlagIcon,
  SearchIcon,
  UserIcon,
} from "../components/icons/Icons";
import { feedbackApi } from "../services/api";
import type { FeedbackItem, FeedbackStats, User } from "../types";

interface AdminFeedbackPageProps {
  currentUser: User | null;
  onNavigateHome: () => void;
  onStatsUpdated?: (stats: FeedbackStats) => void;
}

export const AdminFeedbackPage: React.FC<AdminFeedbackPageProps> = ({
  currentUser,
  onNavigateHome,
  onStatsUpdated,
}) => {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [limit] = useState(15);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [emailStatusFilter, setEmailStatusFilter] = useState<string>("all");

  // Detail Modal
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

  const isAdmin = currentUser?.role === "admin";

  const loadData = useCallback(async () => {
    if (!isAdmin) return;
    setIsLoading(true);
    setError(null);
    try {
      const [statsData, listData] = await Promise.all([
        feedbackApi.getStats(),
        feedbackApi.listFeedback({
          page,
          limit,
          status: statusFilter,
          category: categoryFilter,
          email_status: emailStatusFilter,
          search: searchQuery,
        }),
      ]);
      setStats(statsData);
      if (onStatsUpdated) {
        onStatsUpdated(statsData);
      }
      setItems(listData.items);
      setTotal(listData.total);
      setPages(listData.pages);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load feedback records.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [isAdmin, page, limit, statusFilter, categoryFilter, emailStatusFilter, searchQuery, onStatsUpdated]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleStatusChange = async (id: string, newStatus: "new" | "reviewing" | "resolved") => {
    setIsUpdatingStatus(true);
    try {
      const updated = await feedbackApi.updateStatus(id, newStatus);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
      if (selectedFeedback && selectedFeedback.id === id) {
        setSelectedFeedback(updated);
      }
      // Refresh stats
      const freshStats = await feedbackApi.getStats();
      setStats(freshStats);
      if (onStatsUpdated) {
        onStatsUpdated(freshStats);
      }
    } catch (err) {
      console.error("Failed to update status:", err);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  };

  if (!isAdmin) {
    return (
      <div className="flex-1 h-full flex flex-col items-center justify-center p-6 bg-[#080808] text-center">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
          <FlagIcon className="w-7 h-7 text-red-400" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Access Restricted</h2>
        <p className="text-neutral-400 text-sm max-w-md mb-6">
          You do not have administrative privileges to view the Nexarion Feedback Dashboard.
        </p>
        <button
          onClick={onNavigateHome}
          className="px-4 py-2 rounded-xl bg-white text-black text-xs font-mono font-medium hover:bg-neutral-200 transition-colors"
        >
          Return to Assistant
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full flex flex-col overflow-y-auto bg-[#080808] text-white">
      {/* Top Header */}
      <div className="sticky top-0 z-20 px-6 py-5 bg-[#080808]/90 backdrop-blur-md border-b border-white/10 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-white">Feedback Management</h1>
            <span className="px-2 py-0.5 rounded-md bg-white/10 border border-white/15 text-[11px] font-mono text-neutral-300">
              Admin
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            Review user-reported issues on AI responses and monitor Resend email notifications.
          </p>
        </div>

        <button
          onClick={() => loadData()}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono text-neutral-300 hover:text-white transition-colors flex items-center gap-1.5"
        >
          <span>Refresh</span>
        </button>
      </div>

      <div className="p-6 max-w-7xl mx-auto w-full space-y-6">
        {/* Metric Cards Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
          <div className="p-4 rounded-xl bg-[#0F0F0F] border border-white/10">
            <span className="text-xs font-mono text-neutral-500 block mb-1">Total Reports</span>
            <span className="text-2xl font-bold text-white font-mono">{stats?.total ?? 0}</span>
          </div>

          <div className="p-4 rounded-xl bg-[#0F0F0F] border border-amber-500/20">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-mono text-amber-400">New Reports</span>
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            </div>
            <span className="text-2xl font-bold text-amber-300 font-mono">{stats?.new_count ?? 0}</span>
          </div>

          <div className="p-4 rounded-xl bg-[#0F0F0F] border border-blue-500/20">
            <span className="text-xs font-mono text-blue-400 block mb-1">Reviewing</span>
            <span className="text-2xl font-bold text-blue-300 font-mono">{stats?.reviewing_count ?? 0}</span>
          </div>

          <div className="p-4 rounded-xl bg-[#0F0F0F] border border-emerald-500/20">
            <span className="text-xs font-mono text-emerald-400 block mb-1">Resolved</span>
            <span className="text-2xl font-bold text-emerald-300 font-mono">{stats?.resolved_count ?? 0}</span>
          </div>

          <div className="p-4 rounded-xl bg-[#0F0F0F] border border-white/10">
            <span className="text-xs font-mono text-neutral-500 block mb-1">Email Delivery</span>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold text-white font-mono">
                {(stats?.total ?? 0) - (stats?.failed_emails ?? 0)}
              </span>
              {(stats?.failed_emails ?? 0) > 0 && (
                <span className="text-xs font-mono text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded border border-red-500/20">
                  {stats?.failed_emails} failed
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="p-4 rounded-xl bg-[#0F0F0F] border border-white/10 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
          <div className="relative flex-1 min-w-[220px]">
            <SearchIcon className="w-4 h-4 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search user, content, conversation..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              className="w-full bg-black/50 border border-white/15 rounded-lg pl-9 pr-3 py-2 text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-white/30 text-xs font-mono"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="bg-black/50 border border-white/15 rounded-lg px-3 py-2 text-neutral-300 focus:outline-none focus:border-white/30 text-xs font-mono"
            >
              <option value="all">All Statuses</option>
              <option value="new">New</option>
              <option value="reviewing">Reviewing</option>
              <option value="resolved">Resolved</option>
            </select>

            {/* Category Filter */}
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="bg-black/50 border border-white/15 rounded-lg px-3 py-2 text-neutral-300 focus:outline-none focus:border-white/30 text-xs font-mono max-w-[170px] truncate"
            >
              <option value="all">All Categories</option>
              <option value="Visual is unhelpful or broken">Visual is unhelpful or broken</option>
              <option value="Incorrect or incomplete">Incorrect or incomplete</option>
              <option value="Not what I asked for">Not what I asked for</option>
              <option value="Slow or buggy">Slow or buggy</option>
              <option value="Style or tone">Style or tone</option>
              <option value="Safety or legal concern">Safety or legal concern</option>
              <option value="Other">Other</option>
            </select>

            {/* Email Filter */}
            <select
              value={emailStatusFilter}
              onChange={(e) => {
                setEmailStatusFilter(e.target.value);
                setPage(1);
              }}
              className="bg-black/50 border border-white/15 rounded-lg px-3 py-2 text-neutral-300 focus:outline-none focus:border-white/30 text-xs font-mono"
            >
              <option value="all">All Emails</option>
              <option value="sent">Sent</option>
              <option value="failed">Failed</option>
              <option value="pending">Pending</option>
            </select>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => loadData()} className="underline hover:text-red-300">
              Retry
            </button>
          </div>
        )}

        {/* Table Content */}
        <div className="rounded-xl border border-white/10 bg-[#0F0F0F] overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-white/[0.02] border-b border-white/10 text-neutral-400 uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-4">Date / Time</th>
                  <th className="py-3 px-4">Reporter</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Comment / Details</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-neutral-500">
                      Loading feedback records...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-neutral-500">
                      No feedback reports found matching your criteria.
                    </td>
                  </tr>
                ) : (
                  items.map((item) => {
                    const formattedDate = new Date(item.created_at).toLocaleString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    });

                    return (
                      <tr key={item.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="py-3 px-4 text-neutral-400 whitespace-nowrap">
                          {formattedDate}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            {item.user?.avatar_url ? (
                              <img
                                src={item.user.avatar_url}
                                alt={item.user.name}
                                className="w-5 h-5 rounded-full object-cover border border-white/10"
                              />
                            ) : (
                              <UserIcon className="w-4 h-4 text-neutral-500" />
                            )}
                            <div className="min-w-0">
                              <span className="text-white block truncate max-w-[140px]">
                                {item.user?.name || "Unknown"}
                              </span>
                              <span className="text-[10px] text-neutral-500 block truncate max-w-[140px]">
                                {item.user?.email || item.user_id}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded-md bg-white/10 text-neutral-300 border border-white/10 text-[11px]">
                            {item.category}
                          </span>
                        </td>
                        <td className="py-3 px-4 max-w-xs">
                          <p className="truncate text-neutral-300 text-xs">
                            {item.details || <span className="text-neutral-500 italic">No details</span>}
                          </p>
                          {item.conversation_title && (
                            <span className="text-[10px] text-neutral-500 block truncate mt-0.5">
                              Conv: {item.conversation_title}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <select
                            value={item.status}
                            disabled={isUpdatingStatus}
                            onChange={(e) =>
                              handleStatusChange(
                                item.id,
                                e.target.value as "new" | "reviewing" | "resolved"
                              )
                            }
                            className={`px-2 py-1 rounded-md text-[11px] font-mono border focus:outline-none cursor-pointer ${
                              item.status === "new"
                                ? "bg-amber-500/10 text-amber-300 border-amber-500/30"
                                : item.status === "reviewing"
                                ? "bg-blue-500/10 text-blue-300 border-blue-500/30"
                                : "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                            }`}
                          >
                            <option value="new">new</option>
                            <option value="reviewing">reviewing</option>
                            <option value="resolved">resolved</option>
                          </select>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] border ${
                              item.email_notification_status === "sent"
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : item.email_notification_status === "failed"
                                ? "bg-red-500/10 text-red-400 border-red-500/20"
                                : "bg-neutral-500/10 text-neutral-400 border-neutral-500/20"
                            }`}
                          >
                            {item.email_notification_status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={() => setSelectedFeedback(item)}
                            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/15 text-neutral-300 hover:text-white transition-colors"
                            title="Inspect details"
                          >
                            <EyeIcon className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          <div className="p-3 border-t border-white/10 bg-white/[0.01] flex items-center justify-between text-xs font-mono text-neutral-400">
            <span>
              Showing {items.length} of {total} reports
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1 || isLoading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded-md bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-white/5 transition-colors"
              >
                Prev
              </button>
              <span>
                Page {page} of {pages}
              </span>
              <button
                disabled={page >= pages || isLoading}
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                className="px-2.5 py-1 rounded-md bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-white/5 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Feedback Detail Inspection Modal */}
      {selectedFeedback && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in"
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-2xl bg-[#0D0D0D] border border-white/20 rounded-2xl p-6 shadow-2xl overflow-y-auto max-h-[90vh] space-y-5"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2.5">
                <span className="px-2.5 py-1 rounded-lg text-xs font-mono bg-white/10 text-white border border-white/15">
                  {selectedFeedback.category}
                </span>
                <span className="text-xs text-neutral-400 font-mono">
                  {new Date(selectedFeedback.created_at).toLocaleString()}
                </span>
              </div>
              <button
                onClick={() => setSelectedFeedback(null)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <CloseIcon className="w-4 h-4" />
              </button>
            </div>

            {/* Reporter Information */}
            <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-white/10 border border-white/15 flex items-center justify-center text-white font-bold">
                  {selectedFeedback.user?.name ? selectedFeedback.user.name[0].toUpperCase() : "U"}
                </div>
                <div>
                  <div className="text-white font-medium">{selectedFeedback.user?.name || "Unknown"}</div>
                  <div className="text-neutral-400 text-[11px]">{selectedFeedback.user?.email || selectedFeedback.user_id}</div>
                </div>
              </div>

              {/* Status Update Buttons */}
              <div className="flex items-center gap-1.5">
                {(["new", "reviewing", "resolved"] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => handleStatusChange(selectedFeedback.id, st)}
                    disabled={isUpdatingStatus}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-mono capitalize transition-all ${
                      selectedFeedback.status === st
                        ? "bg-white text-black font-semibold"
                        : "bg-white/5 text-neutral-400 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {/* User Comment / Details */}
            <div>
              <span className="text-xs font-mono text-neutral-400 block mb-1.5">User Comment:</span>
              <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-mono text-neutral-200 whitespace-pre-wrap">
                {selectedFeedback.details || "No optional details provided by user."}
              </div>
            </div>

            {/* Reported AI Response */}
            <div>
              <div className="flex items-center justify-between text-xs font-mono text-neutral-400 mb-1.5">
                <span>Reported AI Response:</span>
                <button
                  onClick={() => copyToClipboard(selectedFeedback.reported_response, "reported")}
                  className="hover:text-white flex items-center gap-1"
                >
                  <CopyIcon className="w-3 h-3" />
                  <span>{copiedId === "reported" ? "Copied" : "Copy"}</span>
                </button>
              </div>
              <div className="p-3.5 rounded-xl bg-black/60 border border-white/15 text-xs font-mono text-neutral-300 max-h-56 overflow-y-auto whitespace-pre-wrap">
                {selectedFeedback.reported_response || "(Empty response)"}
              </div>
            </div>

            {/* Metadata & Technical References */}
            <div className="p-3.5 rounded-xl bg-black/40 border border-white/10 text-[11px] font-mono text-neutral-500 space-y-1">
              <div>Feedback ID: <span className="text-neutral-400">{selectedFeedback.id}</span></div>
              <div>Conversation ID: <span className="text-neutral-400">{selectedFeedback.conversation_ref || "N/A"}</span></div>
              <div>Message ID: <span className="text-neutral-400">{selectedFeedback.message_ref || "N/A"}</span></div>
              <div>
                Resend Status:{" "}
                <span className={selectedFeedback.email_notification_status === "sent" ? "text-emerald-400" : "text-amber-400"}>
                  {selectedFeedback.email_notification_status}
                </span>
                {selectedFeedback.email_sent_at && ` (at ${new Date(selectedFeedback.email_sent_at).toLocaleTimeString()})`}
                {selectedFeedback.email_error && ` - Error: ${selectedFeedback.email_error}`}
              </div>
            </div>

            {/* Footer */}
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedFeedback(null)}
                className="px-4 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-mono text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
