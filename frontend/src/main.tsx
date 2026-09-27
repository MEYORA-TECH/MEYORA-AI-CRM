import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";

import { App } from "./App";
import { ApiError } from "./services/api";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data changed by this user is refreshed right after each save; this only covers other people's edits.
      staleTime: 60_000,
      gcTime: 15 * 60_000,
      refetchOnWindowFocus: false,
      // Don't retry requests the server rejected on purpose.
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider delayDuration={300}>
          <App />
        </TooltipProvider>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          className: "!rounded-2xl !border-[var(--glass-edge)] !bg-[var(--glass-3)] !text-[var(--ink)] !backdrop-blur-xl !font-sans",
        }}
      />
    </QueryClientProvider>
  </StrictMode>,
);
