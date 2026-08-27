import { useEffect, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import type { TreeNode } from "../../api/types"
import { getTree } from "../../api/client"
import { languageIcon } from "../../utils/style"
import "./FileTree.css"

export function FileTree() {
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getTree()
      .then((t) => {
        if (!cancelled) setTree(t)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load tree")
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <nav className="file-tree scroll-y" aria-label="File tree">
      <div className="file-tree-header">Files</div>
      {error && <div className="file-tree-error">{error}</div>}
      {!tree && !error && <div className="file-tree-loading">Loading…</div>}
      {tree?.children && (
        <ul className="file-tree-list">
          {tree.children.map((child) => (
            <TreeEntry key={child.path} node={child} depth={0} />
          ))}
        </ul>
      )}
    </nav>
  )
}

function TreeEntry({ node, depth }: { node: TreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1)
  const navigate = useNavigate()
  const location = useLocation()

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          className="tree-row tree-dir"
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => setOpen((o) => !o)}
        >
          <span className={`disclosure ${open ? "open" : ""}`}>▸</span>
          <span className="tree-name">{node.name}</span>
        </button>
        {open && node.children && (
          <ul>
            {node.children.map((child) => (
              <TreeEntry key={child.path} node={child} depth={depth + 1} />
            ))}
          </ul>
        )}
      </li>
    )
  }

  const href = `/file/${node.path}`
  const active = location.pathname === href

  return (
    <li>
      <button
        type="button"
        className={`tree-row tree-file ${active ? "active" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 + 14 }}
        onClick={() => navigate(href)}
        title={node.path}
      >
        <span className="lang-tag" data-lang={node.language ?? ""}>
          {languageIcon(node.language)}
        </span>
        <span className="tree-name">{node.name}</span>
      </button>
    </li>
  )
}
