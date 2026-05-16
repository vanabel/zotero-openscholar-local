/**
 * 渲染前规范化：LaTeX 定界符、全角星号等（跳过围栏代码块）。
 */
export function normalizeMathDelimiters(markdown: string): string {
  const parts = markdown.split(/(```[\s\S]*?```)/g);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part;
      return (
        part
          .replace(/\\\[([\s\S]*?)\\\]/g, (_, body: string) => `\n\n$$\n${body.trim()}\n$$\n\n`)
          .replace(/\\\(([\s\S]*?)\\\)/g, (_, body: string) => "$" + body.trim() + "$")
          .replace(/＊/g, "*")
      );
    })
    .join("");
}
