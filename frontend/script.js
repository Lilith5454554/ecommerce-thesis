/*function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
        return JSON.parse(jsonPayload);
    } catch(e) {
        return null;
    }
}


// 后端API网关地址
const API_BASE = 'http://localhost:8000';
let authToken = null;  // 存储JWT token

// 辅助函数：发送请求
async function request(endpoint, method, body = null, needAuth = false) {
    const headers = {
        'Content-Type': 'application/json',
    };
    if (needAuth) {
        if (!authToken) {
            throw new Error('未登录，请先登录');
        }
        headers['Authorization'] = `Bearer ${authToken}`;
        // 添加 X-User-ID 头（从登录后保存的 currentUserId 获取）
        if (window.currentUserId) {
            headers['X-User-ID'] = window.currentUserId;
        } else {
            throw new Error('无法获取用户ID，请重新登录');
        }
    }
    const options = {
        method,
        headers,
    };
    if (body) {
        options.body = JSON.stringify(body);
    }
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    if (!response.ok) {
        const error = await response.text();
        throw new Error(`请求失败: ${response.status} ${error}`);
    }
    return response.json();
}

// 注册
document.getElementById('registerBtn').onclick = async () => {
    const username = document.getElementById('regUsername').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    if (!username || !email || !password) {
        alert('请填写完整信息');
        return;
    }
    try {
        const data = await request('/users/', 'POST', { username, email, password });
        alert(`注册成功！用户ID: ${data.id}`);
    } catch (err) {
        alert(`注册失败: ${err.message}`);
    }
};

// 登录
document.getElementById('loginBtn').onclick = async () => {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) {
        alert('请填写用户名和密码');
        return;
    }
    try {
        const data = await request('/auth/login', 'POST', { username, password });
        authToken = data.access_token;

        // 解析 token 获取用户 ID
        const payload = parseJwt(authToken);
        const userId = payload ? payload.sub : null;
        if (userId) {
            // 保存到全局变量（例如 window.currentUserId）
            window.currentUserId = userId;
        }


        document.getElementById('userInfo').innerHTML = `已登录: ${username} (Token 已保存)`;
        alert('登录成功！');
    } catch (err) {
        alert(`登录失败: ${err.message}`);
    }
};

// 刷新商品列表
document.getElementById('listProductsBtn').onclick = async () => {
    try {
        const products = await request('/products/', 'GET');
        const listEl = document.getElementById('productList');
        listEl.innerHTML = '';
        products.forEach(p => {
            const li = document.createElement('li');
            li.textContent = `${p.name} - 价格: ¥${p.price} - 库存: ${p.stock} (ID: ${p.id})`;
            listEl.appendChild(li);
        });
    } catch (err) {
        alert(`获取商品失败: ${err.message}`);
    }
};

// 创建商品（需要登录？根据你的后端，商品创建接口通常不需要认证，但为了安全可以不加）
document.getElementById('createProductBtn').onclick = async () => {
    const name = document.getElementById('prodName').value;
    const price = parseFloat(document.getElementById('prodPrice').value);
    const stock = parseInt(document.getElementById('prodStock').value);
    if (!name || isNaN(price) || isNaN(stock)) {
        alert('请填写完整的商品信息');
        return;
    }
    try {
        const data = await request('/products/', 'POST', { name, price, stock });
        alert(`商品创建成功！ID: ${data.id}`);
        // 刷新列表
        document.getElementById('listProductsBtn').click();
    } catch (err) {
        alert(`创建商品失败: ${err.message}`);
    }
};

// 创建订单（需要认证）
document.getElementById('createOrderBtn').onclick = async () => {
    if (!authToken) {
        alert('请先登录');
        return;
    }
    const productId = document.getElementById('orderProductId').value;
    const quantity = parseInt(document.getElementById('orderQuantity').value);
    const address = document.getElementById('shippingAddress').value;
    if (!productId || isNaN(quantity) || !address) {
        alert('请填写完整订单信息');
        return;
    }
    try {
        // 需要先获取商品详情以得到 product_name 和 price，简化：假设商品存在且价格已知
        // 更好的做法是先调用 /products/{id} 获取商品信息
        const product = await request(`/products/${productId}`, 'GET');
        const orderData = {
            user_id: window.currentUserId,
            items: [{
                product_id: productId,
                product_name: product.name,
                quantity: quantity,
                price: product.price
            }],
            shipping_address: address
        };
        const result = await request('/orders', 'POST', orderData, true);
        document.getElementById('orderResult').innerHTML = `订单创建成功！订单ID: ${result.id}, 总金额: ¥${result.total_amount}`;
    } catch (err) {
        alert(`创建订单失败: ${err.message}`);
    }
};*/

// 后端API网关地址
const API_BASE = 'http://localhost:8000';
let authToken = null;  // 存储JWT token
let currentUserId = null;  // 存储当前登录用户ID

// 辅助函数：发送请求
async function request(endpoint, method, body = null, needAuth = false) {
    const headers = {
        'Content-Type': 'application/json',
    };
    if (needAuth && authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    const options = {
        method,
        headers,
    };
    if (body) {
        options.body = JSON.stringify(body);
    }
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    if (!response.ok) {
        const error = await response.text();
        throw new Error(`请求失败: ${response.status} ${error}`);
    }
    return response.json();
}

// 解析JWT获取用户ID
function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
        return JSON.parse(jsonPayload);
    } catch(e) {
        return null;
    }
}

// 注册
document.getElementById('registerBtn').onclick = async () => {
    const username = document.getElementById('regUsername').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    if (!username || !email || !password) {
        alert('请填写完整信息');
        return;
    }
    try {
        const data = await request('/users/', 'POST', { username, email, password });
        alert(`注册成功！用户ID: ${data.id}`);
    } catch (err) {
        alert(`注册失败: ${err.message}`);
    }
};

// 登录
document.getElementById('loginBtn').onclick = async () => {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) {
        alert('请填写用户名和密码');
        return;
    }
    try {
        const data = await request('/auth/login', 'POST', { username, password });
        authToken = data.access_token;

        // 解析 token 获取用户 ID
        const payload = parseJwt(authToken);
        currentUserId = payload ? payload.sub : null;

        document.getElementById('userInfo').innerHTML = `已登录: ${username} (Token 已保存)`;
        alert('登录成功！');

        // 登录成功后自动刷新订单列表
        if (currentUserId) {
            refreshOrderList();
        }
    } catch (err) {
        alert(`登录失败: ${err.message}`);
    }
};

// 刷新商品列表
document.getElementById('listProductsBtn').onclick = async () => {
    try {
        const products = await request('/products/', 'GET');
        const listEl = document.getElementById('productList');
        listEl.innerHTML = '';
        products.forEach(p => {
            const li = document.createElement('li');
            li.textContent = `${p.name} - 价格: ¥${p.price} - 库存: ${p.stock} (ID: ${p.id})`;
            listEl.appendChild(li);
        });
    } catch (err) {
        alert(`获取商品失败: ${err.message}`);
    }
};

// 创建商品
document.getElementById('createProductBtn').onclick = async () => {
    const name = document.getElementById('prodName').value;
    const price = parseFloat(document.getElementById('prodPrice').value);
    const stock = parseInt(document.getElementById('prodStock').value);
    if (!name || isNaN(price) || isNaN(stock)) {
        alert('请填写完整的商品信息');
        return;
    }
    try {
        const data = await request('/products/', 'POST', { name, price, stock });
        alert(`商品创建成功！ID: ${data.id}`);
        // 刷新列表
        document.getElementById('listProductsBtn').click();
    } catch (err) {
        alert(`创建商品失败: ${err.message}`);
    }
};

// 刷新订单列表
async function refreshOrderList() {
    if (!authToken || !currentUserId) {
        document.getElementById('orderList').innerHTML = '<p>请先登录</p>';
        return;
    }

    try {
        const orders = await request('/orders/', 'GET', null, true);
        const orderListEl = document.getElementById('orderList');

        if (orders.length === 0) {
            orderListEl.innerHTML = '<p>暂无订单</p>';
            return;
        }

        // 只显示当前用户的订单
        const userOrders = orders.filter(o => o.user_id === currentUserId);

        if (userOrders.length === 0) {
            orderListEl.innerHTML = '<p>暂无订单</p>';
            return;
        }

        let html = '<table style="width:100%; border-collapse: collapse;">';
        html += '<tr style="background:#f0f0f0;"><th>订单ID</th><th>总金额</th><th>状态</th><th>收货地址</th><th>创建时间</th><th>操作</th><tr>';

        for (const order of userOrders) {
            // 只有 pending 或 reserved 状态的订单可以取消
            const canCancel = order.status === 'pending' || order.status === 'reserved';

            html += `<tr style="border-bottom:1px solid #ddd;">`;
            html += `<td style="padding:8px; font-size:12px;">${order.id}</td>`;
            html += `<td style="padding:8px;">¥${order.total_amount}</td>`;
            html += `<td style="padding:8px;">${order.status}</td>`;
            html += `<td style="padding:8px;">${order.shipping_address}</td>`;
            html += `<td style="padding:8px; font-size:12px;">${new Date(order.created_at).toLocaleString()}</td>`;
            html += `<td style="padding:8px;">`;
            if (canCancel) {
                html += `<button class="cancel-order-btn" data-id="${order.id}" style="background:#f44336; color:white; border:none; padding:4px 8px; border-radius:4px; cursor:pointer;">取消订单</button>`;
            } else {
                html += `<span style="color:#999;">不可取消</span>`;
            }
            html += `</td></tr>`;
        }
        html += '</table>';
        orderListEl.innerHTML = html;

        // 绑定取消按钮事件
        document.querySelectorAll('.cancel-order-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const orderId = btn.dataset.id;
                await cancelOrder(orderId);
            });
        });

    } catch (err) {
        console.error('获取订单列表失败:', err);
        document.getElementById('orderList').innerHTML = '<p>获取订单列表失败，请确保已登录</p>';
    }
}

// 取消订单
async function cancelOrder(orderId) {
    if (!authToken) {
        alert('请先登录');
        return;
    }

    if (!confirm('确定要取消这个订单吗？取消后库存将恢复。')) {
        return;
    }

    try {
        const result = await request(`/orders/${orderId}/cancel`, 'POST', null, true);
        alert(`订单已取消！${result.message || ''}`);
        // 刷新订单列表
        refreshOrderList();
        // 刷新商品列表（库存已恢复）
        document.getElementById('listProductsBtn').click();
    } catch (err) {
        alert(`取消订单失败: ${err.message}`);
    }
}

// 创建订单
document.getElementById('createOrderBtn').onclick = async () => {
    if (!authToken) {
        alert('请先登录');
        return;
    }
    const productId = document.getElementById('orderProductId').value;
    const quantity = parseInt(document.getElementById('orderQuantity').value);
    const address = document.getElementById('shippingAddress').value;
    if (!productId || isNaN(quantity) || !address) {
        alert('请填写完整订单信息');
        return;
    }
    try {
        const product = await request(`/products/${productId}`, 'GET');
        const orderData = {
            user_id: currentUserId,
            items: [{
                product_id: productId,
                product_name: product.name,
                quantity: quantity,
                price: product.price
            }],
            shipping_address: address
        };
        const result = await request('/orders/', 'POST', orderData, true);
        document.getElementById('orderResult').innerHTML = `订单创建成功！订单ID: ${result.id}, 总金额: ¥${result.total_amount}`;

        // 刷新订单列表
        refreshOrderList();
        // 刷新商品列表（库存已变化）
        document.getElementById('listProductsBtn').click();

    } catch (err) {
        alert(`创建订单失败: ${err.message}`);
    }
};

// 添加刷新订单列表的按钮事件
document.getElementById('listOrdersBtn').onclick = () => {
    refreshOrderList();
};