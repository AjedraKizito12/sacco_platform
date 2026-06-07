import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./Tooltip";

describe("Tooltip", () => {
  it("renders trigger in closed state", () => {
    render(
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>Hover me</TooltipTrigger>
          <TooltipContent>Tooltip content</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    // jsdom does not reliably fire hover focus events for Radix Tooltip.
    // The trigger should always be rendered; that's the smoke we assert.
    expect(screen.getByText("Hover me")).toBeInTheDocument();
  });
});
