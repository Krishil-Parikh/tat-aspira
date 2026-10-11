"use client";

import * as React from "react";
import { GripVerticalIcon } from "lucide-react";

import { cn } from "./utils";

// Simplified resizable components without react-resizable-panels dependency
function ResizablePanelGroup({
  className,
  children,
  direction = "horizontal",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  direction?: "horizontal" | "vertical";
}) {
  return (
    <div
      data-slot="resizable-panel-group"
      className={cn(
        "flex h-full w-full",
        direction === "vertical" ? "flex-col" : "flex-row",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

function ResizablePanel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="resizable-panel"
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border bg-background",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

function ResizableHandle({
  className,
  withHandle,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  withHandle?: boolean;
}) {
  return (
    <div
      data-slot="resizable-handle"
      className={cn(
        "relative flex w-px items-center justify-center bg-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="absolute inset-y-0 left-1/2 w-3 -translate-x-1/2 border border-border bg-background">
          <GripVerticalIcon className="relative left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
