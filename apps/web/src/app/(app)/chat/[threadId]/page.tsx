import { Suspense } from "react";
import { ThreadScreen } from "@/features/threads/thread-screen";

/*
 * The page stays synchronous and hands the thread id to the screen once params resolve.
 * This is the Next.js 16 pattern for dynamic params with Cache Components
 * (node_modules/next/dist/docs/01-app/02-guides/interactive-apps.md, step 1).
 */
export default function ChatPage({ params }: PageProps<"/chat/[threadId]">) {
  return <Suspense fallback={null}>{params.then(({ threadId }) => <ThreadScreen threadId={threadId} />)}</Suspense>;
}
