import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { runs, signals } from "@/lib/fixtures";
import { RunsTable } from "./RunsTable";

const bodyRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);

describe("<RunsTable />", () => {
  it("renders every run, attention first", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    expect(bodyRows()).toHaveLength(13);
    expect(within(bodyRows()[0]!).getByText(/\(דורש בירור\)/)).toBeInTheDocument();
  });

  it("filters by run status", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    await userEvent.click(screen.getByRole("button", { name: /^נכשלה/ }));
    expect(bodyRows()).toHaveLength(3);
    expect(screen.getByRole("button", { name: /^נכשלה/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("filters to runs that need attention from the summary card", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    await userEvent.click(screen.getByRole("button", { name: /5 ריצות/ }));
    expect(bodyRows()).toHaveLength(5);
  });

  it("shows an empty state with a reset when nothing matches", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    await userEvent.click(screen.getByRole("button", { name: /^בריצה/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /רק ריצות שדורשות בירור/ }));
    expect(screen.getByText("אין ריצות שתואמות לסינון")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ניקוי סינון" }));
    expect(bodyRows()).toHaveLength(13);
  });

  it("shows an empty state when there is no data at all", () => {
    render(<RunsTable runs={[]} />);
    expect(screen.getByText("אין עדיין ריצות")).toBeInTheDocument();
  });

  it("marks the total as a lower bound plus an open reservation — never an upper bound", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    expect(screen.getByText("$6.0715")).toBeInTheDocument();
    expect(screen.getByText(/לפחות/, { selector: "dd span" })).toBeInTheDocument();
    const total = screen.getByText("הוצאה כוללת").nextElementSibling!;
    expect(total).toHaveTextContent("+ $0.2600 בשריון פתוח");
    expect(total.textContent).not.toMatch(/עד/);
    expect(screen.queryByText("$6.3315")).not.toBeInTheDocument();
  });

  it("the total is not final while a run is still running", () => {
    render(<RunsTable runs={runs.filter((r) => r.run_id === "run-5d02b8")} signals={signals} />);
    expect(screen.getByText("הוצאה כוללת").nextElementSibling).toHaveTextContent(/^לפחות/);
  });

  it("labels the section with an always-present heading, even when the filter is empty", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    expect(screen.getByRole("region", { name: "רשימת הריצות" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^בריצה/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /רק ריצות שדורשות בירור/ }));
    expect(screen.getByText("אין ריצות שתואמות לסינון")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "רשימת הריצות" })).toBeInTheDocument();
  });

  it("moves focus to the 'all' filter after resetting an empty filter", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    await userEvent.click(screen.getByRole("button", { name: /^בריצה/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /רק ריצות שדורשות בירור/ }));
    await userEvent.click(screen.getByRole("button", { name: "ניקוי סינון" }));
    expect(screen.getByRole("button", { name: /^הכול/ })).toHaveFocus();
  });

  it("the attention summary button is a named toggle", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    const btn = screen.getByRole("button", { name: "הצג רק 5 ריצות שדורשות בירור" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(bodyRows()).toHaveLength(5);
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "false");
    expect(bodyRows()).toHaveLength(13);
  });

  it("hides decorative glyphs in the summary from screen readers", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    for (const glyph of ["✖", "▲", "◔"]) {
      const el = screen.getByText(glyph, { selector: "dd *" });
      expect(el).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("the first cell of each row is a row header", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    expect(screen.getAllByRole("rowheader")).toHaveLength(13);
    for (const r of bodyRows()) {
      const first = r.firstElementChild!;
      expect(first.tagName).toBe("TH");
      expect(first).toHaveAttribute("scope", "row");
    }
  });

  it("status filter counts follow the attention-only switch", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    expect(screen.getByRole("button", { name: "הכול (13)" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /רק ריצות שדורשות בירור/ }));
    expect(screen.getByRole("button", { name: "הכול (5)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "נכשלה (3)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "הושלמה (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "הושלמה חלקית (1)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^בריצה/ })).not.toBeInTheDocument();
  });

  it("keeps the selected status filter visible even when its count drops to 0", async () => {
    render(<RunsTable runs={runs} signals={signals} />);
    await userEvent.click(screen.getByRole("button", { name: /^בריצה/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /רק ריצות שדורשות בירור/ }));
    expect(screen.getByRole("button", { name: "בריצה (0)" })).toHaveAttribute("aria-pressed", "true");
  });

  it("isolates the technical failure reason in <bdi>", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    const el = screen.getByText("provider timeout after 600s");
    expect(el.tagName).toBe("BDI");
    expect(el.closest("li")).toHaveTextContent("הריצה נכשלה: provider timeout after 600s");
  });

  it("each reason carries the icon of its own tone", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    const rowOf = (id: string) => bodyRows().find((r) => within(r).queryByText(id))!;
    expect(within(rowOf("run-11ab02")).getByText("ⓘ")).toHaveAttribute("aria-hidden", "true");
    expect(within(rowOf("run-77de40")).getByText("⚠")).toHaveAttribute("aria-hidden", "true");
    expect(within(rowOf("run-6b8823")).getAllByText("✖")[0]).toHaveAttribute("aria-hidden", "true");
    expect(within(rowOf("run-6b8823")).getByText("חלקית — התקציב מוצה")).toBeInTheDocument();
  });

  it("never renders 'null' / 'undefined' / 'NaN'", () => {
    const zeroInitial = { ...runs.find((r) => r.run_id === "run-2c91e7")!, run_id: "run-zero", initial_budget_usd: "0.000000" };
    const { container } = render(<RunsTable runs={[...runs, zeroInitial]} signals={signals} />);
    expect(container.textContent).not.toMatch(/null|undefined|NaN/);
  });

  it("never relies on colour alone: verdicts carry words", () => {
    render(<RunsTable runs={runs} signals={signals} />);
    const overrunRow = bodyRows().find((r) => within(r).queryByText("run-b41055"))!;
    expect(within(overrunRow).getByText("חריגה מהתקרה")).toBeInTheDocument();
    expect(within(overrunRow).getByText("446%")).toBeInTheDocument();
  });

  it("links rows when runHref is provided", () => {
    render(<RunsTable runs={runs} signals={signals} runHref={(id) => `/runs/${id}`} />);
    expect(screen.getByRole("link", { name: "ניתוח תמחור מתחרים לקראת השקה" })).toHaveAttribute(
      "href",
      "/runs/run-77de40",
    );
  });
});
