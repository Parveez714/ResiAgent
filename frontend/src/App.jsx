import React, { useState, useEffect, useRef } from 'react';
import { 
  Building2, 
  RefreshCw, 
  Search, 
  Download, 
  ChevronDown, 
  AlertTriangle,
  Layers,
  FileCheck,
  BadgeAlert,
  Coins,
  Receipt,
  ArrowRightLeft,
  TrendingUp,
  Database
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  // Tabs and general navigation
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'data'
  const [activeDataTab, setActiveDataTab] = useState('api1'); // 'api1' | 'api2'

  // Data states
  const [projects, setProjects] = useState([]);
  const [selectedProjects, setSelectedProjects] = useState([]);
  const [kpis, setKpis] = useState(null);
  const [tableData1, setTableData1] = useState([]);
  const [tableData2, setTableData2] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Loading and Error states
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  
  // Custom dropdown state
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState('');
  const dropdownRef = useRef(null);

  // Dashboards & charts states
  const [perspectives, setPerspectives] = useState([]);
  const [selectedPerspective, setSelectedPerspective] = useState('');
  const [charts, setCharts] = useState([]);
  const [chartsLoading, setChartsLoading] = useState(false);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch initial configuration & data
  useEffect(() => {
    loadDashboardData();
  }, []);

  // Re-fetch metrics and data when selected projects change
  useEffect(() => {
    fetchMetricsAndData(selectedProjects);
  }, [selectedProjects]);

  // Fetch charts when perspective or selected projects change
  useEffect(() => {
    if (selectedPerspective) {
      fetchCharts(selectedPerspective, selectedProjects);
    }
  }, [selectedPerspective, selectedProjects]);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch Projects List
      const projRes = await fetch(`${API_BASE_URL}/api/projects`);
      if (!projRes.ok) throw new Error('Failed to fetch project list.');
      const projList = await projRes.json();
      setProjects(projList);

      // 2. Fetch Perspectives
      const perspRes = await fetch(`${API_BASE_URL}/api/perspectives`);
      if (perspRes.ok) {
        const perspList = await perspRes.json();
        setPerspectives(perspList);
        if (perspList.length > 0) {
          setSelectedPerspective(perspList[0]);
        }
      }

      // 3. Fetch KPI metrics and portfolios
      await fetchMetricsAndData(selectedProjects);
      
      // 4. Fetch API 2 Data
      const data2Res = await fetch(`${API_BASE_URL}/api/data2`);
      if (data2Res.ok) {
        const detailedData2 = await data2Res.json();
        setTableData2(detailedData2);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetricsAndData = async (selectedProjs) => {
    try {
      const queryParams = new URLSearchParams();
      selectedProjs.forEach(p => queryParams.append('projects', p));

      // Fetch KPIs
      const kpisRes = await fetch(`${API_BASE_URL}/api/kpis?${queryParams.toString()}`);
      if (!kpisRes.ok) throw new Error('Failed to load KPIs.');
      const kpisData = await kpisRes.json();
      setKpis(kpisData);

      // Fetch detailed table data (API 1)
      const dataRes = await fetch(`${API_BASE_URL}/api/data?${queryParams.toString()}`);
      if (!dataRes.ok) throw new Error('Failed to load project details.');
      const detailedData = await dataRes.json();
      setTableData1(detailedData);
    } catch (err) {
      setError(err.message);
    }
  };

  const fetchCharts = async (perspective, selectedProjs) => {
    setChartsLoading(true);
    try {
      const queryParams = new URLSearchParams();
      queryParams.append('perspective', perspective);
      selectedProjs.forEach(p => queryParams.append('projects', p));

      const chartsRes = await fetch(`${API_BASE_URL}/api/charts?${queryParams.toString()}`);
      if (chartsRes.ok) {
        const chartsData = await chartsRes.json();
        setCharts(chartsData);
      }
    } catch (err) {
      console.error("Failed to load charts:", err);
    } finally {
      setChartsLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const syncRes = await fetch(`${API_BASE_URL}/api/sync`, { method: 'POST' });
      if (!syncRes.ok) throw new Error('Synchronization failed.');
      await loadDashboardData();
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const toggleProject = (project) => {
    if (selectedProjects.includes(project)) {
      setSelectedProjects(selectedProjects.filter(p => p !== project));
    } else {
      setSelectedProjects([...selectedProjects, project]);
    }
  };

  const selectAllProjects = () => {
    setSelectedProjects([]);
  };

  const clearAllProjects = () => {
    setSelectedProjects([]);
  };

  const formatCurrency = (val, prefix = "₹") => {
    if (val === null || val === undefined) return `${prefix}0`;
    const absVal = Math.abs(val);
    let formatted = "";
    if (absVal >= 10000000) {
      formatted = `${Math.round(val / 10000000)} Cr`;
    } else if (absVal >= 100000) {
      formatted = `${Math.round(val / 100000)} L`;
    } else if (absVal >= 1000) {
      formatted = `${Math.round(val / 1000)}K`;
    } else {
      formatted = Math.round(val).toString();
    }
    return `${prefix}${formatted}`;
  };

  // Filter projects inside the custom dropdown
  const filteredDropdownProjects = projects.filter(p => 
    p.toLowerCase().includes(dropdownSearch.toLowerCase())
  );

  // Filter table records by search term
  const activeDataset = tableData1;
  const filteredTableRecords = activeDataset.filter(record => {
    const projName = (record.Project_Name || record.Partner_Name || record.PartnerName || record.ProjectName || '').toLowerCase();
    const sector = (record.Sector || record.Collection_Type || '').toLowerCase();
    const search = searchTerm.toLowerCase();
    return projName.includes(search) || sector.includes(search);
  });

  // Export filtered data as CSV
  const handleExportCSV = () => {
    if (filteredTableRecords.length === 0) return;
    
    const headers = Object.keys(filteredTableRecords[0]);
    const csvRows = [];
    
    // Add headers
    csvRows.push(headers.join(','));
    
    // Add data rows
    for (const row of filteredTableRecords) {
      const values = headers.map(header => {
        const val = row[header];
        const escaped = ('' + (val ?? '')).replace(/"/g, '""');
        return `"${escaped}"`;
      });
      csvRows.push(values.join(','));
    }
    
    const csvContent = "data:text/csv;charset=utf-8," + csvRows.join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", 'portfolio_data.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Render dynamic SVG charts based on backend spec
  const renderSVGChart = (chartSpec) => {
    const data = chartSpec.data || [];
    const chartType = chartSpec.chart_type;

    if (data.length === 0) {
      return <div className="text-center p-8 text-gray-500 text-xs">No chart data matching focus parameters</div>;
    }

    const maxVal = Math.max(...data.map(d => d.value), 1);

    if (chartType === 'pie') {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
          {data.map((d, i) => {
            const pct = Math.round((d.value / maxVal) * 100);
            return (
              <div key={i} style={{ fontSize: '0.8rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9ca3af', marginBottom: '2px' }}>
                  <span className="truncate" style={{ maxWidth: '180px' }}>{d.name}</span>
                  <span>{formatCurrency(d.value)}</span>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(to right, #10b981, #34d399)', borderRadius: '4px' }}></div>
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    if (chartType === 'line' || chartType === 'scatter') {
      const points = data.map((d, i) => {
        const x = (i / (data.length - 1 || 1)) * 260 + 20;
        const y = 130 - (d.value / maxVal) * 100;
        return { x, y, name: d.name, val: d.value };
      });
      const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

      return (
        <div style={{ position: 'relative', width: '100%', height: '150px' }}>
          <svg viewBox="0 0 300 150" style={{ width: '100%', height: '100%' }}>
            <line x1="20" y1="30" x2="280" y2="30" stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
            <line x1="20" y1="80" x2="280" y2="80" stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
            <line x1="20" y1="130" x2="280" y2="130" stroke="rgba(255,255,255,0.1)" />
            <path d={pathD} fill="none" stroke="#60a5fa" strokeWidth="2.5" />
            {points.map((p, idx) => (
              <g key={idx}>
                <circle cx={p.x} cy={p.y} r="4" fill="#3b82f6" stroke="#030712" strokeWidth="1.5" />
                <title>{`${p.name}: ${formatCurrency(p.val)}`}</title>
              </g>
            ))}
          </svg>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: '#6b7280', padding: '0 10px' }}>
            <span className="truncate" style={{ maxWidth: '80px' }}>{data[0]?.name}</span>
            <span className="truncate" style={{ maxWidth: '80px' }}>{data[data.length - 1]?.name}</span>
          </div>
        </div>
      );
    }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', width: '100%' }}>
        {data.map((d, i) => {
          const pct = Math.round((d.value / maxVal) * 100);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
              <span className="truncate" style={{ width: '80px', color: '#9ca3af', textAlign: 'right' }}>{d.name}</span>
              <div style={{ flex: 1, height: '14px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', overflow: 'hidden', position: 'relative' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(to right, #3b82f6, #60a5fa)', borderRadius: '4px' }}></div>
              </div>
              <span style={{ width: '60px', color: '#f8fafc', fontWeight: '500' }}>{formatCurrency(d.value)}</span>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar glass-panel">
        <div className="sidebar-brand">
          <Building2 className="w-8 h-8 text-sky-400" />
          <div>
            <h2>Resi Revenue</h2>
            <p>Real-Time Board Metrics</p>
          </div>
        </div>

        <div className="sidebar-divider"></div>

        {/* Project Selector Box above navigation buttons */}
        <div className="selector-box" ref={dropdownRef} style={{ width: '100%' }}>
          <label className="selector-label">Project Filter (Multi-Select)</label>
          <div className="dropdown-container">
            <div 
              className={`dropdown-trigger ${dropdownOpen ? 'active' : ''}`}
              onClick={() => setDropdownOpen(!dropdownOpen)}
            >
              <span className="truncate">
                {selectedProjects.length === 0 
                  ? 'All Projects Selected' 
                  : `${selectedProjects.length} Selected`}
              </span>
              <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
            </div>
            
            {dropdownOpen && (
              <div className="dropdown-menu">
                <input 
                  type="text" 
                  className="dropdown-search" 
                  placeholder="Search projects..."
                  value={dropdownSearch}
                  onChange={(e) => setDropdownSearch(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                />
                <div className="dropdown-actions">
                  <button className="btn-link" onClick={(e) => { e.stopPropagation(); selectAllProjects(); }}>
                    Reset (All)
                  </button>
                  <button className="btn-link text-red-400" onClick={(e) => { e.stopPropagation(); clearAllProjects(); }}>
                    Clear All
                  </button>
                </div>
                <div className="dropdown-list">
                  {filteredDropdownProjects.length === 0 ? (
                    <div className="p-2 text-center text-xs text-gray-500">No projects found</div>
                  ) : (
                    filteredDropdownProjects.map(proj => {
                      const isSelected = selectedProjects.includes(proj);
                      return (
                        <div 
                          key={proj} 
                          className={`dropdown-item ${isSelected ? 'selected' : ''}`}
                          onClick={(e) => { e.stopPropagation(); toggleProject(proj); }}
                        >
                          <div className="checkbox-custom"></div>
                          <span className="truncate">{proj}</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Tab Navigation in Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
          <button 
            className={`btn-secondary ${activeTab === 'dashboard' ? 'active-tab-btn' : ''}`}
            onClick={() => setActiveTab('dashboard')}
            style={{ justifyContent: 'flex-start', width: '100%', background: activeTab === 'dashboard' ? 'rgba(59, 130, 246, 0.15)' : '', borderColor: activeTab === 'dashboard' ? 'var(--primary)' : '' }}
          >
            <TrendingUp className="w-4 h-4 text-sky-400" />
            <span>Board Dashboard</span>
          </button>
          <button 
            className={`btn-secondary ${activeTab === 'data' ? 'active-tab-btn' : ''}`}
            onClick={() => setActiveTab('data')}
            style={{ justifyContent: 'flex-start', width: '100%', background: activeTab === 'data' ? 'rgba(59, 130, 246, 0.15)' : '', borderColor: activeTab === 'data' ? 'var(--primary)' : '' }}
          >
            <Database className="w-4 h-4 text-indigo-400" />
            <span>Live Data Statements</span>
          </button>
        </div>

        <div className="sidebar-divider"></div>

        <div className="sidebar-footer" style={{ marginTop: 'auto' }}>
          <button 
            className="btn-secondary btn-sync-sidebar" 
            onClick={handleSync}
            disabled={syncing || loading}
            style={{ width: '100%' }}
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Syncing...' : 'Sync Live Data'}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        {/* Top Header */}
        <header className="glass-panel dashboard-header">
          <div className="header-title-section">
            <h1>🏢 Executive Project Portal</h1>
            <p>Real-Time Board Metrics & Inventory Performance</p>
          </div>
        </header>

        {/* Error Alert Box */}
        {error && (
          <div className="error-banner">
            <AlertTriangle className="w-6 h-6 text-red-500" />
            <div>
              <strong>Operational Error:</strong> {error}
            </div>
          </div>
        )}



        {/* Main Tab Content views */}
        {loading ? (
          <div className="loading-overlay">
            <div className="spinner"></div>
            <p className="text-gray-400 font-medium">Fetching portfolios and aggregation metrics...</p>
          </div>
        ) : (
          <>
            {/* 📊 TAB 1: Dashboard View */}
            {activeTab === 'dashboard' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                
                {/* KPIs Grid - Maintained exactly as requested */}
                <section className="kpis-grid">
                  {/* Total Units */}
                  <div className="glass-panel kpi-card indigo">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Total Units</span>
                      <div className="kpi-card-icon">
                        <Layers className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{(kpis?.total_units ?? 0).toLocaleString()}</div>
                    <span className="kpi-card-desc">Total project inventory units</span>
                  </div>

                  {/* Sold */}
                  <div className="glass-panel kpi-card emerald">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Sold Units</span>
                      <div className="kpi-card-icon">
                        <FileCheck className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{(kpis?.sold ?? 0).toLocaleString()}</div>
                    <span className="kpi-card-desc">Booked and signed units</span>
                  </div>

                  {/* Unsold */}
                  <div className="glass-panel kpi-card rose">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Unsold Units</span>
                      <div className="kpi-card-icon">
                        <BadgeAlert className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{(kpis?.unsold ?? 0).toLocaleString()}</div>
                    <span className="kpi-card-desc">Available unit stock</span>
                  </div>

                  {/* Sold Value */}
                  <div className="glass-panel kpi-card emerald">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Sold Value</span>
                      <div className="kpi-card-icon">
                        <Coins className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{formatCurrency(kpis?.sold_value ?? 0)}</div>
                    <span className="kpi-card-desc">Total booked sales revenue</span>
                  </div>

                  {/* Unsold Value */}
                  <div className="glass-panel kpi-card rose">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Unsold Value</span>
                      <div className="kpi-card-icon">
                        <AlertTriangle className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{formatCurrency(kpis?.unsold_value ?? 0)}</div>
                    <span className="kpi-card-desc">Estimated value of vacant units</span>
                  </div>

                  {/* Invoiced */}
                  <div className="glass-panel kpi-card blue">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Invoiced Amt</span>
                      <div className="kpi-card-icon">
                        <Receipt className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{formatCurrency(kpis?.invoiced ?? 0)}</div>
                    <span className="kpi-card-desc">Total milestones invoiced to date</span>
                  </div>

                  {/* Receipt Amt */}
                  <div className="glass-panel kpi-card emerald">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Receipt Amt</span>
                      <div className="kpi-card-icon">
                        <Coins className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{formatCurrency(kpis?.received ?? 0)}</div>
                    <span className="kpi-card-desc">Total collection/receipts to date</span>
                  </div>

                  {/* Uninvoiced */}
                  <div className="glass-panel kpi-card rose">
                    <div className="kpi-card-header">
                      <span className="kpi-card-title">Uninvoiced Amt</span>
                      <div className="kpi-card-icon">
                        <ArrowRightLeft className="w-5 h-5" />
                      </div>
                    </div>
                    <div className="kpi-card-value">{formatCurrency(kpis?.uninvoiced ?? 0)}</div>
                    <span className="kpi-card-desc">Balance sales value to invoice</span>
                  </div>
                </section>

                {/* Perspective selector & dynamic charts */}
                <section className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                    <div>
                      <h2 style={{ margin: 0, fontSize: '1.25rem', fontFamily: 'Outfit, sans-serif' }}>📊 Interactive Board Insights</h2>
                      <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>Dynamic visual charts generated based on the selected focus area</span>
                    </div>
                    <div>
                      <select 
                        value={selectedPerspective} 
                        onChange={(e) => setSelectedPerspective(e.target.value)}
                        style={{ background: '#111827', border: '1px solid var(--border-color)', color: '#f8fafc', padding: '0.6rem 1rem', borderRadius: '8px', fontSize: '0.9rem', outline: 'none', cursor: 'pointer' }}
                      >
                        {perspectives.map((p, idx) => (
                          <option key={idx} value={p}>{p}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {chartsLoading ? (
                    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
                      <div className="spinner"></div>
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
                      {charts.map((c, i) => (
                        <div key={i} className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem', border: '1px solid rgba(255,255,255,0.05)' }}>
                          <span style={{ fontWeight: '600', fontSize: '0.9rem', color: '#cbd5e1' }}>{c.title}</span>
                          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '160px' }}>
                            {renderSVGChart(c)}
                          </div>
                          {c.insight && (
                            <div style={{ background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.1)', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.75rem', color: '#93c5fd' }}>
                              💡 <b>Strategic note:</b> {c.insight}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}

            {/* 📄 TAB 3: Live API Data Statements */}
            {activeTab === 'data' && (
              <section className="glass-panel data-table-container">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
                  <div className="search-input-wrapper" style={{ minWidth: '300px' }}>
                    <Search className="search-icon w-4 h-4" />
                    <input 
                      type="text" 
                      className="search-input" 
                      placeholder="Search project or sector..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                  </div>
                  
                  <button 
                    className="btn-secondary" 
                    onClick={handleExportCSV}
                    disabled={filteredTableRecords.length === 0}
                    style={{ padding: '0.75rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    title="Export CSV"
                  >
                    <Download className="w-5 h-5" />
                  </button>
                </div>

                <div className="table-wrapper">
                  {filteredTableRecords.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No project records match the current search filters.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Project Name</th>
                          <th>Total Inventory</th>
                          <th>Sold Inventory</th>
                          <th>Available Inventory</th>
                          <th>Total Sales Value</th>
                          <th>Total Invoiced</th>
                          <th>Balance to Invoice</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredTableRecords.slice(0, 150).map((row, idx) => (
                          <tr key={idx}>
                            <td style={{ fontWeight: '600' }}>{row.Project_Name || 'N/A'}</td>
                            <td>{(row.TotalInventory ?? 0).toLocaleString()}</td>
                            <td>{(row.SoldInventory ?? 0).toLocaleString()}</td>
                            <td>{(row.AvailableInventory ?? 0).toLocaleString()}</td>
                            <td>{formatCurrency(row.TotalSalesRealization ?? 0)}</td>
                            <td>{formatCurrency(row.TotalInvoiced ?? 0)}</td>
                            <td>{formatCurrency(row.BalanceToBeInvoiced ?? 0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                {filteredTableRecords.length > 150 && (
                  <div className="pt-3 text-center text-xs text-gray-500">
                    Showing top 150 project records. Use search/filter to narrow down results.
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
