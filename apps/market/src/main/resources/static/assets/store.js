const $=(selector)=>document.querySelector(selector);
const $$=(selector)=>[...document.querySelectorAll(selector)];
const cartId=localStorage.getItem('northstar-cart')||crypto.randomUUID();
localStorage.setItem('northstar-cart',cartId);
const state={category:'all',query:'',cart:null,priority:'balanced'};
const money=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'});
const accents={green:'#246b45',gold:'#cc8b2c',coral:'#d65f4b',berry:'#9a3e61',navy:'#193552',sky:'#4a8ea1',red:'#a8453e',teal:'#217f78',plum:'#70445f'};
let csrf;

async function json(url,options={}){
  const method=(options.method||'GET').toUpperCase();
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  if(!['GET','HEAD','OPTIONS'].includes(method)){
    csrf=csrf||await fetch('/api/security/csrf').then(response=>response.json());
    headers[csrf.headerName]=csrf.token;
  }
  const response=await fetch(url,{...options,headers});
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.error||`Request failed (${response.status})`)}
  return response.json();
}

async function loadProducts(){
  const params=new URLSearchParams({category:state.category,query:state.query});
  const data=await json(`/api/catalog/products?${params}`);
  renderProducts(data.items);
}

function renderProducts(items){
  $('#result-count').textContent=`${items.length} products available at Riverfront`;
  $('#product-grid').innerHTML=items.map(product=>`
    <article class="product-card">
      <div class="product-art" style="--accent:${accents[product.accent]||accents.green}">
        <img src="${product.image}" alt="">
        <span class="product-badge">${escapeHtml(product.badge)}</span>
        <span class="stock">${product.stock<45?'LOW STOCK':product.stock+' AVAILABLE'}</span>
        <button class="favorite" aria-label="Save ${escapeHtml(product.name)}">♡</button>
      </div>
      <div class="product-body">
        <span class="product-maker">${escapeHtml(product.maker)}</span>
        <h3>${escapeHtml(product.name)}</h3>
        <p>${escapeHtml(product.summary)}</p>
        <div class="spec-pills">${Object.entries(product.specs).slice(0,2).map(([key,value])=>`<span><b>${escapeHtml(key)}</b> ${escapeHtml(value)}</span>`).join('')}</div>
        <div class="product-price"><div><strong>${money.format(product.price)}</strong><s>${money.format(product.compareAtPrice)}</s></div><button class="add-button" data-add="${product.sku}">Add</button></div>
      </div>
    </article>`).join('');
  $$('[data-add]').forEach(button=>button.addEventListener('click',()=>addToCart(button.dataset.add)));
  $$('.product-art img').forEach(image=>image.addEventListener('error',()=>image.style.display='none'));
}

async function loadCart(){state.cart=await json(`/api/cart/${cartId}`);renderCart()}
async function addToCart(sku){
  try{
    state.cart=await json(`/api/cart/${cartId}/items`,{method:'POST',body:JSON.stringify({sku,quantity:1})});
    renderCart();toast('Added to your Northstar basket');openCart();
  }catch(error){toast(error.message)}
}
async function removeFromCart(sku){state.cart=await json(`/api/cart/${cartId}/items/${sku}`,{method:'DELETE'});renderCart()}

function renderCart(){
  const cart=state.cart||{lines:[],itemCount:0,subtotal:0};
  $('#cart-count').textContent=cart.itemCount;
  $('#cart-total').textContent=money.format(cart.subtotal);
  $('#cart-lines').innerHTML=cart.lines.length?cart.lines.map(line=>`
    <div class="cart-line">
      <img src="${line.image}" alt="">
      <div><strong>${escapeHtml(line.name)}</strong><span>${line.quantity} × ${money.format(line.unitPrice)}</span><small>Substitutions: contact me</small></div>
      <button data-remove="${line.sku}" aria-label="Remove ${escapeHtml(line.name)}">×</button>
    </div>`).join(''):'<div class="cart-empty"><i>✦</i><strong>Your basket is ready for something good.</strong><span>Explore today’s fresh picks and meal solutions.</span></div>';
  $$('[data-remove]').forEach(button=>button.addEventListener('click',()=>removeFromCart(button.dataset.remove)));
}

async function submitAdvisor(event){
  event.preventDefault();
  const result=$('#advisor-result');
  result.hidden=false;
  result.innerHTML='<span>Checking live inventory and your preferences…</span>';
  try{
    const data=await json('/api/advisor/recommend',{method:'POST',body:JSON.stringify({workload:$('#advisor-workload').value,budget:Number($('#advisor-budget').value),priority:state.priority})});
    result.innerHTML=`<small>GROUNDED PLAN · CURRENT INVENTORY</small><strong>${escapeHtml(data.title)}</strong><span>${escapeHtml(data.explanation)}</span><em>${escapeHtml(data.platformUpgrade)}</em>`;
  }catch(error){result.innerHTML=`<span>${escapeHtml(error.message)}</span>`}
}

async function loadPlatform(){
  try{
    const platform=await json('/api/platform');
    $('#platform-app').textContent=platform.application;
    $('#platform-runtime').textContent=platform.runtime;
    $('#platform-database').textContent=platform.database;
    $('#platform-route').textContent=platform.route;
    $('#platform-instance').textContent=`Instance ${platform.instance} · ${platform.deploymentMode}`;
    $('#platform-services').innerHTML=platform.capabilities.map(service=>`
      <div class="service-evidence-row" data-status="${escapeHtml(service.status)}">
        <i></i><span><b>${escapeHtml(service.name)}</b><small>${escapeHtml(service.role)}</small></span><em>${escapeHtml(service.implementation)}</em>
      </div>`).join('');
    platform.capabilities.forEach(service=>{
      const chip=document.querySelector(`[data-capability="${service.id}"]`);
      if(chip)chip.dataset.status=service.status;
    });
  }catch{$('#platform-instance').textContent='Platform evidence unavailable'}
}

function openCart(open=true){$('#cart-drawer').classList.toggle('open',open);$('#drawer-scrim').classList.toggle('open',open);$('#cart-drawer').setAttribute('aria-hidden',String(!open))}
function toast(message){const element=$('#toast');element.textContent=message;element.classList.add('show');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>element.classList.remove('show'),2200)}
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]))}

$('#category-tabs').addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  $$('#category-tabs button').forEach(item=>item.classList.toggle('active',item===button));
  state.category=button.dataset.category;loadProducts();
});
$('#catalog-search').addEventListener('input',event=>{clearTimeout(window.searchTimer);window.searchTimer=setTimeout(()=>{state.query=event.target.value;loadProducts()},180)});
$('#search-toggle').addEventListener('click',()=>{$('#shop').scrollIntoView();setTimeout(()=>$('#catalog-search').focus(),350)});
$('#cart-toggle').addEventListener('click',()=>openCart());
$('#cart-close').addEventListener('click',()=>openCart(false));
$('#drawer-scrim').addEventListener('click',()=>openCart(false));
$$('[data-priority]').forEach(button=>button.addEventListener('click',()=>{$$('[data-priority]').forEach(item=>item.classList.toggle('active',item===button));state.priority=button.dataset.priority}));
$('#advisor-form').addEventListener('submit',submitAdvisor);
$('#checkout-button').addEventListener('click',()=>toast(state.cart?.itemCount?'Secure checkout is ready for the ordering chapter.':'Add an item before reviewing your order.'));

Promise.all([loadProducts(),loadCart(),loadPlatform()]).catch(error=>toast(error.message));
