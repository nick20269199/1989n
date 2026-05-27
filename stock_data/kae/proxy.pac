function FindProxyForURL(url, host) {
    // Only proxy WeChat-related traffic
    if (host.endsWith('.qq.com') || 
        host.endsWith('.wechat.com') ||
        host.endsWith('.weixin.qq.com') ||
        host == 'localhost' ||
        host == '127.0.0.1') {
        return 'PROXY 127.0.0.1:8080';
    }
    // Everything else goes direct
    return 'DIRECT';
}
