import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    // 查找挂载点 - 支持多个可能的ID
    const mountPoints = ['#vue-dashboard', '#app'];
    let mountEl = null;
    
    for (const selector of mountPoints) {
        mountEl = document.querySelector(selector);
        if (mountEl) break;
    }
    
    if (mountEl) {
        const app = createApp(App);
        app.use(router);
        app.mount(mountEl);
    } else {
        console.error('Vue应用挂载点未找到');
    }
});