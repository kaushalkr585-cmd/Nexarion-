export function formatSelectionPrompt(selectedText: string): string {
  const clean = selectedText.trim();
  if (!clean) return "";

  const isCode =
    clean.includes("\n") ||
    /^(def |class |function |const |let |var |import |export |async |SELECT |FROM |CREATE |if |for |while |return )/m.test(
      clean
    ) ||
    /[{};:=><]/.test(clean);

  if (isCode) {
    return `Explain this code and how it works:\n\n\`\`\`\n${clean}\n\`\`\``;
  }

  return `Explain this statement in simple terms:\n\n"${clean}"`;
}

export function isTargetExcluded(element: Node | null): boolean {
  if (!element) return false;
  const isElement =
    typeof Node !== "undefined" ? element.nodeType === Node.ELEMENT_NODE : element.nodeType === 1;
  const el = isElement ? (element as Element) : element.parentElement;
  if (!el || typeof el.closest !== "function") return false;

  return Boolean(
    el.closest(
      'input, textarea, [contenteditable="true"], button, select, [role="button"], .ask-nexarion-floating-btn, .nexarion-context-menu, [data-exclude-selection="true"]'
    )
  );
}
