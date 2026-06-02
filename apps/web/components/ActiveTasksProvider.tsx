"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { useActiveTasks, type ActiveTaskRow } from "@/lib/useActiveTasks";
import type { TaskStreamEvent } from "@/lib/api";

type ActiveTasksContextValue = ReturnType<typeof useActiveTasks>;

type TaskFinishedEvent = Extract<TaskStreamEvent, { type: "task_status" }>;

type ActiveTaskListeners = {
  onAllIdle?: () => void;
  onTaskFinished?: (ev: TaskFinishedEvent) => void;
};

const ActiveTasksContext = createContext<ActiveTasksContextValue | null>(null);
const ListenersRefContext = createContext<
  React.MutableRefObject<ActiveTaskListeners> | null
>(null);

/** 全站共享一条任务 SSE，供文献库与顶栏队列横幅使用。 */
export function ActiveTasksProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef<ActiveTaskListeners>({});
  const value = useActiveTasks({
    onAllIdle: () => listenersRef.current.onAllIdle?.(),
    onTaskFinished: (ev) => listenersRef.current.onTaskFinished?.(ev),
  });

  return (
    <ListenersRefContext.Provider value={listenersRef}>
      <ActiveTasksContext.Provider value={value}>{children}</ActiveTasksContext.Provider>
    </ListenersRefContext.Provider>
  );
}

export function useSharedActiveTasks(): ActiveTasksContextValue {
  const ctx = useContext(ActiveTasksContext);
  if (!ctx) {
    throw new Error("useSharedActiveTasks must be used within ActiveTasksProvider");
  }
  return ctx;
}

/** 页面级回调（如文献库任务结束后刷新列表），不影响 SSE 单例。 */
export function useActiveTaskListeners(listeners: ActiveTaskListeners): void {
  const listenersRef = useContext(ListenersRefContext);
  if (!listenersRef) {
    throw new Error("useActiveTaskListeners must be used within ActiveTasksProvider");
  }
  useEffect(() => {
    listenersRef.current = listeners;
    return () => {
      listenersRef.current = {};
    };
  }, [listeners.onAllIdle, listeners.onTaskFinished, listenersRef]);
}

export type { ActiveTaskRow, TaskFinishedEvent };
