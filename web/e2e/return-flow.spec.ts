import { expect, test } from "@playwright/test";

test("login, stream a return request, approve, and create a ticket", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "订单历史" })).toContainText("order-1001");
  await expect(page.getByRole("region", { name: "订单历史" })).toContainText("delivered");
  const send = page.getByRole("button", { name: "发送请求" });
  await expect(send).toBeEnabled();
  await send.click();

  await expect(page.getByText("approval_required", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "批准" }).click();
  await expect(page.getByText("已批准，工单已创建。", { exact: false })).toBeVisible();
  await expect(page.getByText("已批准，工单已创建。", { exact: false })).toHaveCount(1);
  if (process.env.CAPTURE_DEMO === "1") {
    await page.screenshot({ path: "../docs/demo-ui.png", fullPage: true });
  }
});
