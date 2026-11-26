import React, { useEffect, useState } from "react";
import { CheckIcon, CloseIcon } from "../icons/Icons";

export const FEEDBACK_CATEGORIES = [
  "Visual is unhelpful or broken",
  "Incorrect or incomplete",
  "Not what I asked for",
  "Slow or buggy",
  "Style or tone",
  "Safety or legal concern",
  "Other",
] as const;

export type FeedbackCategory = (typeof FEEDBACK_CATEGORIES)[number];

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    category: FeedbackCategory;
    details?: string;
    messageId: string;
    reportedResponse: string;
  }) => Promise<void>;
  messageId: string;
  reportedResponse: string;
}

export const FeedbackModal: React.FC<FeedbackModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  messageId,
  reportedResponse,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<FeedbackCategory>(
    FEEDBACK_CATEGORIES[0]
  );
  const [details, setDetails] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSelectedCategory(FEEDBACK_CATEGORIES[0]);
      setDetails("");
      setIsSubmitting(false);
      setIsSuccess(false);
      setErrorMessage(null);
    }
  }, [isOpen, messageId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await onSubmit({
        category: selectedCategory,
        details: details.trim() || undefined,
        messageId,
        reportedResponse,
      });
      setIsSuccess(true);
      setTimeout(() => {
        onClose();
      }, 1800);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit feedback. Please try again.";
      setErrorMessage(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-dialog-title"
    >
      <div
        className="w-full max-w-md bg-[#0D0D0D] border border-white/15 rounded-2xl p-6 shadow-2xl relative overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div>
            <h2
              id="feedback-dialog-title"
              className="text-base font-semibold text-white tracking-tight"
            >
              Provide Feedback
            </h2>
            <p className="text-xs text-neutral-400 mt-0.5">
              Help improve Nexarion&apos;s responses and accuracy
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>

        {isSuccess ? (
          <div className="py-8 flex flex-col items-center justify-center text-center animate-fade-in">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-3">
              <CheckIcon className="w-6 h-6 text-emerald-400" />
            </div>
            <h3 className="text-sm font-semibold text-white">Thank you for your feedback!</h3>
            <p className="text-xs text-neutral-400 max-w-xs mt-1.5">
              Thanks for helping me improve Nexarion. I&apos;ll personally review your feedback.
            </p>
            <button
              type="button"
              onClick={onClose}
              className="mt-5 px-4 py-1.5 rounded-lg text-xs font-mono bg-white/10 hover:bg-white/20 text-white transition-colors"
            >
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            {/* Category selection */}
            <div>
              <label className="block text-xs font-mono text-neutral-300 mb-2">
                What went wrong?
              </label>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {FEEDBACK_CATEGORIES.map((cat) => {
                  const isSelected = selectedCategory === cat;
                  return (
                    <button
                      type="button"
                      key={cat}
                      onClick={() => setSelectedCategory(cat)}
                      className={`w-full text-left px-3 py-2 rounded-xl text-xs font-mono transition-all flex items-center justify-between border ${
                        isSelected
                          ? "bg-white/15 text-white border-white/30 font-medium"
                          : "bg-white/[0.03] text-neutral-400 border-white/5 hover:bg-white/[0.08] hover:text-neutral-200"
                      }`}
                    >
                      <span>{cat}</span>
                      {isSelected && <div className="w-2 h-2 rounded-full bg-white shrink-0 ml-2" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Optional details */}
            <div>
              <div className="flex items-center justify-between text-xs font-mono text-neutral-400 mb-1.5">
                <span>Details</span>
                <span className="text-[10px] text-neutral-500">{details.length}/2000</span>
              </div>
              <textarea
                value={details}
                onChange={(e) => setDetails(e.target.value.slice(0, 2000))}
                placeholder="Share details (optional)"
                rows={3}
                disabled={isSubmitting}
                className="w-full bg-black/60 border border-white/15 rounded-xl p-3 text-xs text-neutral-200 placeholder-neutral-500 font-mono resize-none focus:outline-none focus:border-white/40 disabled:opacity-50"
              />
            </div>

            {errorMessage && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono">
                {errorMessage}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-white/10">
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
                className="px-3.5 py-2 rounded-xl text-xs font-mono text-neutral-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-2 rounded-xl text-xs font-mono font-medium bg-white text-black hover:bg-neutral-200 active:scale-95 transition-all disabled:opacity-40 disabled:hover:bg-white disabled:active:scale-100 flex items-center gap-1.5 cursor-pointer"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                    <span>Submitting...</span>
                  </>
                ) : (
                  <span>Submit Feedback</span>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
