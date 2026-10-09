// Lucide (ISC) icons, bundled and tree-shaken by esbuild so only the nodes
// imported below are inlined into the self-contained mesh.html — no runtime fetch.
import {
  createElement,
  MessagesSquare,
  ArrowDownLeft,
  ArrowUpRight,
  RefreshCw,
  ArrowLeft,
  UserPlus,
  MessageSquare,
  Send,
  Sparkles,
  CalendarRange,
} from 'lucide';

// Builds a decorative inline SVG. Icons are always paired with visible text, so
// they are aria-hidden and unfocusable, keeping each control's accessible name
// equal to its label text.
export function icon(node, className, size = 16) {
  const svg = createElement(node);
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  if (className) svg.setAttribute('class', className);
  return svg;
}

export {
  MessagesSquare,
  ArrowDownLeft,
  ArrowUpRight,
  RefreshCw,
  ArrowLeft,
  UserPlus,
  MessageSquare,
  Send,
  Sparkles,
  CalendarRange,
};
