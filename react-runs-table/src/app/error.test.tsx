import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorView from "./error";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("<ErrorView />", () => {
  beforeEach(() => refresh.mockClear());

  it("shows a fixed message and the digest, never the raw error message", () => {
    const error = Object.assign(new Error("ENOENT: open 'C:\\secret\\data\\runs.json'"), { digest: "4102938475" });
    render(<ErrorView error={error} reset={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("לא הצלחנו לטעון את הריצות");
    expect(screen.queryByText(/ENOENT/)).not.toBeInTheDocument();
    expect(screen.getByText("4102938475")).toBeInTheDocument();
  });

  it("retry re-fetches the server data and resets the boundary", async () => {
    const reset = vi.fn();
    render(<ErrorView error={new Error("boom")} reset={reset} />);
    await userEvent.click(screen.getByRole("button", { name: "לנסות שוב" }));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
