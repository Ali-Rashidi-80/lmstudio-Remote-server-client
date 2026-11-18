import { expect, Page, test } from "@playwright/test";

const ADMIN_USER = process.env.E2E_ADMIN_USER || "admin";
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || "adminpass12";

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByPlaceholder("مثال: admin").fill(ADMIN_USER);
  await page.getByPlaceholder("حداقل ۱۰ کاراکتر").fill(ADMIN_PASS);
  await page.getByRole("button", { name: "ورود" }).click();
  await expect(page).toHaveURL(/\/chat$/);
}

test.describe("AI Workspace E2E (Real Chrome + Bridge)", () => {
  test("self-contained local fonts & logo, zero external CDNs, zero console errors, RTL & theme toggle", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const externalHosts: string[] = [];

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("request", (req) => {
      try {
        const u = new URL(req.url());
        if (u.hostname !== "127.0.0.1" && u.hostname !== "localhost") {
          externalHosts.push(u.href);
        }
      } catch {
        /* ignore data: / blob: */
      }
    });

    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);

    // Clear initial unauthenticated probe errors from / redirect and assert 0 console errors on /login
    consoleErrors.length = 0;
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "ورود به حساب" })).toBeVisible();

    const htmlDir = await page.locator("html").getAttribute("dir");
    expect(htmlDir).toBe("rtl");

    // Verify local brand logo & local woff2 fonts load cleanly
    const logoResp = await page.request.get("/logo.png");
    expect(logoResp.status()).toBe(200);
    const fontResp = await page.request.get("/fonts/Vazirmatn-Regular.woff2");
    expect(fontResp.status()).toBe(200);

    // Toggle theme Light <-> Dark
    const beforeTheme = await page.locator("html").getAttribute("data-theme");
    await page.getByRole("button", { name: /تم روشن|تم تاریک/ }).click();
    const afterTheme = await page.locator("html").getAttribute("data-theme");
    expect(afterTheme).not.toBe(beforeTheme);

    expect(externalHosts).toEqual([]);
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
  });

  test("login and full /chat CRUD (create, rename dialog, export links, delete dialog)", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await loginAsAdmin(page);

    const createResPromise = page.waitForResponse(
      (res) => res.url().endsWith("/api/chats") && res.request().method() === "POST"
    );
    await page.getByRole("button", { name: "+ گفتگوی جدید" }).click();
    const createRes = await createResPromise;
    expect(createRes.status()).toBe(200);
    const createdChat = (await createRes.json()) as { id: string };

    const chatTitle = `QA Browser Chat ${Date.now()}`;
    await page.getByRole("button", { name: "تغییر نام" }).click();

    const dialog = page.locator("dialog.native-dialog[open]");
    await expect(dialog).toBeVisible();
    await dialog.locator("input").fill(chatTitle);
    const patchPromise = page.waitForResponse(
      (res) =>
        res.url().endsWith(`/api/chats/${createdChat.id}`) && res.request().method() === "PATCH"
    );
    await dialog.getByRole("button", { name: "ذخیره" }).click();
    expect((await patchPromise).status()).toBe(200);
    await expect(dialog).toBeHidden();

    await expect(page.locator(".topbar-title")).toHaveText(chatTitle);

    // Verify export endpoints return HTTP 200 for the created chat
    const mdHref = await page.getByRole("link", { name: "خروجی MD" }).getAttribute("href");
    const jsonHref = await page.getByRole("link", { name: "خروجی JSON" }).getAttribute("href");
    expect(mdHref).toContain("/export?format=md");
    expect(jsonHref).toContain("/export?format=json");

    const mdRes = await page.request.get(mdHref!);
    expect(mdRes.status()).toBe(200);
    expect(await mdRes.text()).toContain(`# ${chatTitle}`);

    const jsonRes = await page.request.get(jsonHref!);
    expect(jsonRes.status()).toBe(200);

    // Delete chat via confirmation dialog
    await page.locator(".chat-item", { hasText: chatTitle }).getByRole("button", { name: "حذف" }).click();
    const delDialog = page.locator("dialog.native-dialog[open]");
    await expect(delDialog).toBeVisible();
    await delDialog.getByRole("button", { name: "حذف گفتگو" }).click();
    await expect(delDialog).toBeHidden();
    await expect(page.locator(".chat-item", { hasText: chatTitle })).toHaveCount(0);

    expect(pageErrors).toEqual([]);
  });

  test("/knowledge UI upload zone, filters, and RAG search form render cleanly", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await loginAsAdmin(page);
    await page.getByRole("link", { name: "پایگاه دانش" }).click();
    await expect(page).toHaveURL(/\/knowledge$/);

    await expect(page.locator(".dropzone")).toBeVisible();
    await expect(page.getByPlaceholder("فیلتر بر اساس عنوان…")).toBeVisible();
    await expect(page.getByPlaceholder("پرسش یا عبارت کلیدی برای بازیابی از اسناد…")).toBeVisible();

    expect(pageErrors).toEqual([]);
  });

  test("/admin dashboard KPIs, dynamic version, invite create/revoke, self-lockout guard, audit filter & prune", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await loginAsAdmin(page);
    await page.getByRole("link", { name: "مدیریت" }).click();
    await expect(page).toHaveURL(/\/admin$/);

    await expect(page.locator(".topbar-title")).toContainText("v20.0.0");

    // Create invite & revoke it via confirmation dialog
    await page.getByRole("button", { name: "ایجاد دعوت‌نامه" }).click();
    await expect(page.getByRole("button", { name: "کپی لینک" }).first()).toBeVisible();

    const revokeBtn = page.getByRole("button", { name: "لغو" }).first();
    await expect(revokeBtn).toBeVisible();
    await revokeBtn.click();
    const revDialog = page.locator("dialog.native-dialog[open]");
    await expect(revDialog).toBeVisible();
    await revDialog.getByRole("button", { name: "تایید" }).click();
    await expect(revDialog).toBeHidden();

    // Admin self-row controls must be disabled
    const adminRow = page.locator("tr", { hasText: "شما" });
    await expect(adminRow.locator("select")).toBeDisabled();
    await expect(adminRow.getByRole("button", { name: /غیرفعال‌سازی|فعال‌سازی/ })).toBeDisabled();

    // Audit filter + maintenance prune
    await page.getByPlaceholder("فیلتر اکشن (مثال: login)").fill("login");
    await expect(page.locator("table").last()).toContainText("login");

    await page.getByRole("button", { name: "پاکسازی لاگ و توکن‌های قدیمی" }).click();
    await expect(page.locator(".toast-stack").getByText(/پاکسازی انجام شد/)).toBeVisible();

    expect(pageErrors).toEqual([]);
  });

  test("mobile responsive viewport drawer opens cleanly without horizontal overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAsAdmin(page);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    );
    expect(overflow).toBe(false);

    await page.getByRole("button", { name: "منو" }).click();
    await expect(page.locator(".sidebar")).toHaveClass(/sidebar--open/);
  });
});
