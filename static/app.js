const { createApp, ref, computed, watch, onMounted, onUnmounted } = Vue;

const serviceCard = {
  template: '#service-card-template',
  props: ['service', 'displayHost'],
  emits: ['toggle-fav', 'check-health', 'set-group'],
  data() {
    return { showGroupInput: false };
  },
  computed: {
    typeLabel() {
      const map = { http: 'HTTP', database: 'DB', cache: 'Cache', mq: 'MQ', infra: 'Infra', unknown: '?' };
      return map[this.service.type] || '?';
    },
    typeBadgeClass() {
      const map = {
        http: 'bg-blue-500/20 text-blue-400',
        database: 'bg-green-500/20 text-green-400',
        cache: 'bg-purple-500/20 text-purple-400',
        mq: 'bg-orange-500/20 text-orange-400',
        infra: 'bg-gray-500/20 text-gray-400',
        unknown: 'bg-gray-500/20 text-gray-400',
      };
      return map[this.service.type] || map.unknown;
    },
    pageTypeLabel() {
      const pt = (this.service.extra && this.service.extra.page_type) || '';
      const map = {
        webpage: { text: '页面', cls: 'bg-emerald-500/20 text-emerald-400' },
        api: { text: 'API', cls: 'bg-cyan-500/20 text-cyan-400' },
        service: { text: '服务', cls: 'bg-gray-600/20 text-gray-400' },
        unreachable: { text: '不可达', cls: 'bg-red-500/20 text-red-400' },
        timeout: { text: '超时', cls: 'bg-yellow-500/20 text-yellow-400' },
      };
      return map[pt] || null;
    },
    healthColor() {
      if (this.service.status === 'healthy') return 'bg-green-400';
      if (this.service.status === 'unhealthy') return 'bg-red-400';
      return 'bg-gray-500';
    },
    computedUrl() {
      if (this.service.type !== 'http') return '';
      const scheme = this.service.port === 443 ? 'https' : 'http';
      var host = this.displayHost;
      if (this.service.host === '127.0.0.1' || this.service.host === 'localhost') {
        host = 'localhost';
      }
      return scheme + '://' + host + ':' + this.service.port;
    },
  },
  methods: {
    copyConnectionString() {
      const svc = this.service;
      var host = this.displayHost;
      if (svc.host === '127.0.0.1' || svc.host === 'localhost') {
        host = 'localhost';
      }
      let text = '';
      if (svc.type === 'http') {
        text = this.computedUrl || ('http://' + host + ':' + svc.port);
      } else if (svc.type === 'database') {
        const portNames = { 3306: 'mysql', 5432: 'postgresql', 27017: 'mongodb', 1521: 'oracle', 1433: 'sqlserver' };
        const scheme = portNames[svc.port] || 'db';
        text = scheme + '://' + host + ':' + svc.port;
      } else if (svc.type === 'cache') {
        if (svc.port === 6379) text = 'redis://' + host + ':6379';
        else if (svc.port === 11211) text = 'memcached://' + host + ':11211';
        else text = host + ':' + svc.port;
      } else {
        text = host + ':' + svc.port;
      }
      navigator.clipboard.writeText(text).then(() => {
        this._toast('已复制: ' + text);
      });
    },
    _toast(msg) {
      const el = document.createElement('div');
      el.textContent = msg;
      el.className = 'fixed bottom-4 right-4 bg-gray-800 text-gray-200 px-4 py-2 rounded-lg text-sm shadow-lg z-50 animate-fade-in';
      document.body.appendChild(el);
      setTimeout(function() { el.remove(); }, 2000);
    },
  },
};

const app = createApp({
  components: { serviceCard },
  setup() {
    const services = ref([]);
    const searchQuery = ref('');
    const activeType = ref('all');
    const activePageType = ref('all');
    const refreshing = ref(false);
    const autoRefreshEnabled = ref(true);
    const refreshInterval = ref(30);
    const selectedIP = ref('localhost');
    const ipList = ref(['localhost']);
    let refreshTimer = null;

    function matchesActivePageType(svc) {
      if (activePageType.value === 'all') return true;
      return svc.type === 'http' && (svc.extra && svc.extra.page_type) === activePageType.value;
    }

    const typeTabs = computed(function() {
      var base = services.value.filter(matchesActivePageType);
      var counts = { all: base.length };
      for (var i = 0; i < base.length; i++) {
        var svc = base[i];
        counts[svc.type] = (counts[svc.type] || 0) + 1;
      }
      return [
        { value: 'all', label: '全部', icon: '📋', count: counts.all },
        { value: 'http', label: 'HTTP', icon: '🌐', count: counts.http || 0 },
        { value: 'database', label: '数据库', icon: '🗄️', count: counts.database || 0 },
        { value: 'cache', label: '缓存', icon: '⚡', count: counts.cache || 0 },
        { value: 'mq', label: '消息队列', icon: '📨', count: counts.mq || 0 },
        { value: 'infra', label: '基础设施', icon: '🔧', count: counts.infra || 0 },
        { value: 'unknown', label: '其他', icon: '❓', count: counts.unknown || 0 },
      ];
    });

    var pageTypeTabs = computed(function() {
      var base = services.value;
      if (activeType.value !== 'all') {
        base = base.filter(function(s) { return s.type === activeType.value; });
      }
      var counts = { all: 0 };
      var defined = { webpage: 0, api: 0, service: 0, unreachable: 0, timeout: 0 };
      for (var i = 0; i < base.length; i++) {
        var svc = base[i];
        var pt = (svc.extra && svc.extra.page_type) || '';
        counts.all++;
        if (pt && defined.hasOwnProperty(pt)) {
          defined[pt]++;
        }
      }
      return [
        { value: 'all', label: '全部', count: counts.all },
        { value: 'webpage', label: '页面', icon: '📄', count: defined.webpage },
        { value: 'api', label: 'API', icon: '🔌', count: defined.api },
        { value: 'service', label: '服务', icon: '⚙️', count: defined.service },
        { value: 'unreachable', label: '不可达', icon: '🚫', count: defined.unreachable },
        { value: 'timeout', label: '超时', icon: '⏱️', count: defined.timeout },
      ];
    });

    watch(activeType, function(t) {
      if (t !== 'all' && t !== 'http') {
        activePageType.value = 'all';
      }
    });

    var filteredServices = computed(function() {
      var list = services.value;
      if (activeType.value !== 'all') {
        list = list.filter(function(s) { return s.type === activeType.value; });
      }
      if (activePageType.value !== 'all') {
        var targetPT = activePageType.value;
        list = list.filter(function(s) { return (s.extra && s.extra.page_type) === targetPT; });
      }
      if (searchQuery.value.trim()) {
        var q = searchQuery.value.toLowerCase().trim();
        list = list.filter(function(s) {
          return s.name.toLowerCase().indexOf(q) >= 0 ||
            String(s.port).indexOf(q) >= 0 ||
            (s.process_name || '').toLowerCase().indexOf(q) >= 0 ||
            (s.container_name || '').toLowerCase().indexOf(q) >= 0;
        });
      }
      return list;
    });

    var visibleGroups = computed(function() {
      var favs = filteredServices.value.filter(function(s) { return s.favorite; });
      var grouped = {};
      var ungrouped = [];

      for (var i = 0; i < filteredServices.value.length; i++) {
        var svc = filteredServices.value[i];
        if (!svc.favorite && svc.group) {
          if (!grouped[svc.group]) grouped[svc.group] = [];
          grouped[svc.group].push(svc);
        } else if (!svc.favorite) {
          ungrouped.push(svc);
        }
      }

      var result = [];
      if (favs.length) result.push({ name: '⭐ 收藏', services: favs });
      var keys = Object.keys(grouped);
      for (var k = 0; k < keys.length; k++) {
        result.push({ name: keys[k], services: grouped[keys[k]] });
      }
      if (ungrouped.length) result.push({ name: '', services: ungrouped });
      return result;
    });

    async function fetchIPs() {
      try {
        var resp = await fetch('/api/ips');
        var data = await resp.json();
        ipList.value = data;
        if (data.indexOf(selectedIP.value) < 0) {
          selectedIP.value = data[0] || 'localhost';
        }
      } catch (e) {
        console.error('获取 IP 列表失败:', e);
      }
    }

    async function fetchServices() {
      try {
        var resp = await fetch('/api/services');
        services.value = await resp.json();
      } catch (e) {
        console.error('获取服务列表失败:', e);
      }
    }

    async function refreshAll() {
      refreshing.value = true;
      try {
        var resp = await fetch('/api/services/refresh', { method: 'POST' });
        services.value = await resp.json();
        await refreshHealth();
      } finally {
        refreshing.value = false;
      }
    }

    async function refreshHealth() {
      try {
        var resp = await fetch('/api/services/refresh-health', { method: 'POST' });
        var results = await resp.json();
        for (var i = 0; i < services.value.length; i++) {
          var svc = services.value[i];
          if (svc.id in results) svc.status = results[svc.id];
        }
      } catch (e) {
        console.error('健康检测失败:', e);
      }
    }

    async function checkHealth(svcId) {
      try {
        var resp = await fetch('/api/services/' + svcId + '/health');
        var result = await resp.json();
        var svc = services.value.find(function(s) { return s.id === svcId; });
        if (svc) svc.status = result.status;
      } catch (e) {
        console.error('健康检测失败:', e);
      }
    }

    async function toggleFavorite(svcId) {
      try {
        var resp = await fetch('/api/favorites/' + svcId, { method: 'PUT' });
        var result = await resp.json();
        var svc = services.value.find(function(s) { return s.id === svcId; });
        if (svc) svc.favorite = result.favorites.indexOf(svcId) >= 0;
        services.value.sort(function(a, b) {
          return (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0) || a.port - b.port;
        });
      } catch (e) {
        console.error('收藏操作失败:', e);
      }
    }

    async function setGroup(svcId, group) {
      try {
        await fetch('/api/services/' + svcId + '/group', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group: group }),
        });
        var svc = services.value.find(function(s) { return s.id === svcId; });
        if (svc) svc.group = group;
      } catch (e) {
        console.error('设置分组失败:', e);
      }
    }

    function startAutoRefresh() {
      stopAutoRefresh();
      if (autoRefreshEnabled.value) {
        refreshTimer = setInterval(function() {
          fetchServices();
        }, refreshInterval.value * 1000);
      }
    }

    function stopAutoRefresh() {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
    }

    onMounted(async function() {
      await fetchIPs();
      await fetchServices();
      startAutoRefresh();
    });

    onUnmounted(function() {
      stopAutoRefresh();
    });

    return {
      services: services,
      searchQuery: searchQuery,
      activeType: activeType,
      activePageType: activePageType,
      pageTypeTabs: pageTypeTabs,
      refreshing: refreshing,
      autoRefreshEnabled: autoRefreshEnabled,
      refreshInterval: refreshInterval,
      selectedIP: selectedIP,
      ipList: ipList,
      typeTabs: typeTabs,
      filteredServices: filteredServices,
      visibleGroups: visibleGroups,
      refreshAll: refreshAll,
      checkHealth: checkHealth,
      toggleFavorite: toggleFavorite,
      setGroup: setGroup,
    };
  },
});

app.mount('#app');
