import { lazy, Suspense } from "react"

const WorkspaceChatView = lazy(() =>
  import("../pages/WorkspaceChatView.tsx").then((module) => ({ default: module.WorkspaceChatView })),
)

export function WorkspaceChatRoute() {
  return (
    <Suspense fallback={<div className="route-loading">Loading chat runtime...</div>}>
      <WorkspaceChatView />
    </Suspense>
  )
}
