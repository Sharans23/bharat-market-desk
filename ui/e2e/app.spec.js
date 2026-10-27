import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
test.beforeEach(async({request})=>{
 const boot=await request.get('/api/bootstrap',{headers:{'X-Requested-With':'IndiaTrader'}});const data=await boot.json();
 for(const name of ['account','targets','prices','instruments','alerts','config']){
  const file=name==='config'?'../../data/default-config.json':`../../examples/workspace/${name}.json`;
  const document=JSON.parse(readFileSync(new URL(file,import.meta.url),'utf8'));
  const response=await request.post('/api/document',{headers:{Origin:process.env.TEST_BASE_URL||'http://127.0.0.1:8765','X-CSRF-Token':data.csrf},data:{workspace:'practice',name,document}});
  expect(response.ok()).toBe(true);
 }
});
test('dashboard and every service page render without browser errors',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'Your market workspace',exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true});
 for(const label of ['Portfolio','Market data','Research','Trade planner','Risk checks','Paper orders','Tax & accounting','Alerts','Connections','Data workspace','How to use']){
  await page.getByRole('navigation').getByRole('button',{name:label,exact:true}).click();
  await expect(page.locator('main h1')).toBeVisible();
  const tabs=page.getByRole('tab');for(let i=0;i<await tabs.count();i++){await tabs.nth(i).click();await expect(page.locator('.tool-form')).toBeVisible()}
 }
 expect(errors).toEqual([]);
 await page.screenshot({path:'test-results/guide-desktop.png',fullPage:true});
});
test('allocation, risk, exact approval and paper fill operate through the UI',async({page})=>{
 await page.goto('/#planning');await page.getByRole('button',{name:'Build allocation',exact:true}).click();
 await expect(page.locator('.results')).toContainText('NSE:INFY');
 await page.getByRole('navigation').getByRole('button',{name:'Risk checks',exact:true}).click();await page.getByRole('button',{name:'Run risk checks'}).click();
 await expect(page.locator('.results')).toContainText('PASS');
 await page.getByRole('navigation').getByRole('button',{name:'Paper orders',exact:true}).click();await page.getByRole('button',{name:'Review tickets',exact:true}).click();
 await page.getByRole('button',{name:'Review ticket',exact:true}).first().click();
 const modal=page.getByRole('dialog');await expect(modal.getByRole('button',{name:'Approve this paper order'})).toBeDisabled();
 await modal.getByRole('checkbox').check();await modal.getByRole('button',{name:'Approve this paper order'}).click();await expect(modal.getByText('Paper approval recorded')).toBeVisible();
 await modal.getByRole('button',{name:'Record paper fill'}).click();await expect(modal).not.toBeVisible();
 await page.getByRole('tab',{name:'Paper activity'}).click();await page.getByRole('button',{name:'Refresh ledger'}).click();await expect(page.locator('.results')).toContainText('BUY');
});
test('financial analysis, screener, disclosure comparison, tax and alert services work',async({page})=>{
 await page.goto('/#research');await page.getByRole('tab',{name:'Financial results',exact:true}).click();await page.getByRole('button',{name:'Analyze results',exact:true}).click();await expect(page.locator('.results')).toContainText('INFY');
 await page.getByRole('tab',{name:'Equity screener',exact:true}).click();await page.getByRole('button',{name:'Run screener'}).click();await expect(page.locator('.results .raw')).toBeVisible();
 await page.getByRole('tab',{name:'Disclosed portfolios',exact:true}).click();await page.getByLabel('Previous holdings (optional)').selectOption('example:holdings-previous');await page.getByRole('button',{name:'Analyze holdings'}).click();await expect(page.locator('.results .raw')).toBeVisible();
 await page.getByRole('navigation').getByRole('button',{name:'Tax & accounting',exact:true}).click();await page.getByRole('button',{name:'Build tax report'}).click();await expect(page.locator('.results .raw')).toBeVisible();
 await page.getByRole('navigation').getByRole('button',{name:'Alerts',exact:true}).click();await page.getByRole('button',{name:'Check alerts now'}).click();await expect(page.locator('.results .raw')).toBeVisible();
});
test('UI uploads and workspace settings persist while workspaces stay separate',async({page})=>{
 await page.goto('/#data');await page.getByLabel('Upload input file').setInputFiles({name:'ui-fixture.json',mimeType:'application/json',buffer:Buffer.from('{"rows":[]}')});await expect(page.locator('.file-list')).toContainText('ui-fixture.json');
 const cap=page.getByLabel('Cash buffer pct');await cap.fill('12');await page.getByRole('button',{name:'Save changes',exact:true}).click();await expect(page.getByRole('status')).toContainText('Completed');await page.reload();await expect(page.getByLabel('Cash buffer pct')).toHaveValue('12');
 await page.getByLabel('Cash buffer pct').fill('10');await page.getByRole('button',{name:'Save changes',exact:true}).click();await expect(page.getByRole('status')).toContainText('Completed');
 await page.getByLabel('Workspace',{exact:true}).selectOption('research');await page.getByRole('navigation').getByRole('button',{name:'Overview',exact:true}).click();await expect(page.getByText('Your watchlist starts here')).toBeVisible();await expect(page.locator('.stat').first()).toContainText('₹0.00');
});
test('broker login starts and cancels from UI without persisting secrets in browser',async({page})=>{
 await page.goto('/#brokers');await page.getByRole('button',{name:'Connect Zerodha Kite'}).click();
 await page.getByLabel('API key',{exact:true}).fill('synthetic-ui-key');await page.getByLabel('API secret · used for this login only').fill('synthetic-ui-secret');await page.getByRole('button',{name:'Start Kite login'}).click();
 const link=page.getByRole('link',{name:'Continue to Zerodha'});await expect(link).toHaveAttribute('href',/^https:\/\/kite\.zerodha\.com\/connect\/login/);
 expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('synthetic-ui');
 await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 await page.getByRole('button',{name:'Connect Dhan',exact:true}).click();await expect(page.getByLabel('Dhan client ID')).toBeVisible();await expect(page.getByLabel('Access token',{exact:true})).toHaveAttribute('type','password');await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 await page.screenshot({path:'test-results/connections-desktop.png',fullPage:true});
});
test('phone layout is usable and has no document overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.locator('main h1')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/overview-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Open navigation'}).click();await page.getByRole('navigation').getByRole('button',{name:'Connections',exact:true}).click();await expect(page.getByRole('heading',{name:'Broker connections',exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Connect Zerodha Kite'}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.screenshot({path:'test-results/login-mobile.png',fullPage:true});
});
test('stop local app shuts down through the UI',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Stop local app',exact:true}).click();
 await page.getByRole('dialog').getByRole('button',{name:'Stop application',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Application stopped',exact:true})).toBeVisible();
});
