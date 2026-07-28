import React, { useState, useEffect, useRef } from 'react';
import { 
  Building2, 
  RefreshCw, 
  Search, 
  Download, 
  ChevronDown, 
  FileText, 
  Check, 
  AlertTriangle,
  BadgeAlert,
  Coins,
  Receipt,
  FileCheck,
  Percent,
  Layers,
  ArrowRightLeft
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjects, setSelectedProjects] = useState([]);
  const [kpis, setKpis] = useState(null);
  const [tableData, setTableData] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  
  // Custom dropdown state
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState('');
  const dropdownRef = useRef(null);

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

  // Fetch initial data
  useEffect(() => {
    loadDashboardData();
  }, []);

  // Re-fetch KPIs and data when selected projects change
  useEffect(() => {
    fetchMetricsAndData(selectedProjects);
  }, [selectedProjects]);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch Projects List
      const projRes = await fetch(`${API_BASE_URL}/api/projects`);
      if (!projRes.ok) throw new Error('Failed to fetch project list.');
      const projList = await projRes.json();
      setProjects(projList);

      // 2. Fetch KPIs and Data
      await fetchMetricsAndData(selectedProjects);
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

      // Fetch detailed table data
      const dataRes = await fetch(`${API_BASE_URL}/api/data?${queryParams.toString()}`);
      if (!dataRes.ok) throw new Error('Failed to load project details.');
      const detailedData = await dataRes.json();
      setTableData(detailedData);
    } catch (err) {
      setError(err.message);
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
  const filteredTableRecords = tableData.filter(record => {
    const projName = (record.Project_Name || '').toLowerCase();
    const sector = (record.Sector || '').toLowerCase();
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
    link.setAttribute("download", `filtered_projects_data.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar glass-panel">
        <div className="sidebar-brand">
          <Building2 className="w-8 h-8 text-sky-400" />
          <div>
            <h2>Resi Revenue Agent</h2>
            <p>Real-Time Board Metrics</p>
          </div>
        </div>

        <div className="sidebar-divider"></div>

        {/* Project Selector & Filter inside Sidebar */}
        <div className="selector-box" ref={dropdownRef}>
          <label className="selector-label">Project Filter (Multi-Select)</label>
          <div className="dropdown-container">
            <div 
              className={`dropdown-trigger ${dropdownOpen ? 'active' : ''}`}
              onClick={() => setDropdownOpen(!dropdownOpen)}
            >
              <span className="truncate">
                {selectedProjects.length === 0 
                  ? 'All Projects Selected' 
                  : `${selectedProjects.length} Projects Selected`}
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

        <div className="sidebar-divider"></div>

        <div className="sidebar-footer" style={{ marginTop: 'auto' }}>
          <button 
            className="btn-secondary btn-sync-sidebar" 
            onClick={handleSync}
            disabled={syncing || loading}
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

        {/* Content Section */}
        {loading ? (
          <div className="loading-overlay">
            <div className="spinner"></div>
            <p className="text-gray-400 font-medium">Fetching portfolios and aggregation metrics...</p>
          </div>
        ) : (
          <>
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

          {/* Details Table view */}
          <section className="glass-panel data-table-container">
            <div className="table-header-controls">
              <div className="search-input-wrapper">
                <Search className="search-icon w-4 h-4" />
                <input 
                  type="text" 
                  className="search-input" 
                  placeholder="Search project name or sector..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <button 
                className="btn-secondary" 
                onClick={handleExportCSV}
                disabled={filteredTableRecords.length === 0}
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>

            <div className="table-wrapper">
              {filteredTableRecords.length === 0 ? (
                <div className="p-8 text-center text-gray-400">No project records match the current filter.</div>
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
          </>
        )}
      </main>
    </div>
  );
}

export default App;
