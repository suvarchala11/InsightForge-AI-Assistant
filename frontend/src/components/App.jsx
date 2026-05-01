import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, LineChart, MessageSquare, Database, FileText } from 'lucide-react';
import { CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis } from 'recharts';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

function App() {
  const [messages, setMessages] = useState([
    { role: 'ai', content: 'Hello! I am InsightForge, your AI Analytics Assistant for the entertainment data. Ask me a question about movie performance, viewer engagement, or marketing campaigns!', traces: [] }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [yearFilter, setYearFilter] = useState('Any');
  const [regionFilter, setRegionFilter] = useState('Any');
  const endOfMessagesRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input, traces: [] };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const contextLines = [];
      if (yearFilter !== 'Any') contextLines.push(`Release year: ${yearFilter}`);
      if (regionFilter !== 'Any') contextLines.push(`Region: ${regionFilter}`);

      const messageToSend = contextLines.length
        ? `${input}\n\nUser-selected filters:\n${contextLines.map((l) => `- ${l}`).join('\n')}`
        : input;

      const response = await axios.post(`${BACKEND_URL}/api/chat`, {
        message: messageToSend,
      });

      setMessages(prev => [...prev, {
        role: 'ai',
        content: response.data.answer,
        traces: response.data.traces || []
      }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'ai',
        content: 'Error: Could not reach the backend server.',
        traces: []
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const renderChart = (trace) => {
    const data = trace.result;
    if (!Array.isArray(data) || data.length === 0) return null;

    const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);
    const isNonEmptyString = (value) => typeof value === 'string' && value.trim().length > 0;

    const keys = Object.keys(data[0] || {});
    const numKeys = keys.filter(k => data.some(row => isFiniteNumber(row?.[k])));
    const stringKeys = keys.filter(k => data.some(row => isNonEmptyString(row?.[k])));

    const preferredXAxisKeys = [
      'title',
      'campaign_name',
      'region',
      'country',
      'genre',
      'channel',
      'age_group',
      'subscription_tier'
    ];

    const preferredBarKeys = [
      'revenue_millions',
      'roi_percent',
      'spend_thousands',
      'conversions',
      'total_viewers',
      'avg_engagement_score',
      'active_days_last_month',
      'rating'
    ];

    const isIdLikeKey = (key) => {
      const normalized = String(key).toLowerCase();
      return normalized === 'id' || normalized.endsWith('_id');
    };

    const pickXAxisKey = () => {
      const preferred = preferredXAxisKeys.find(k => stringKeys.includes(k));
      if (preferred) return preferred;

      let bestKey = stringKeys[0];
      let bestDistinct = -1;
      for (const k of stringKeys) {
        const distinct = new Set(
          data.map(row => row?.[k]).filter(isNonEmptyString)
        ).size;
        if (distinct > bestDistinct) {
          bestDistinct = distinct;
          bestKey = k;
        }
      }
      return bestKey;
    };

    const pickBarKey = () => {
      const candidateNumKeys = numKeys.filter(k => !isIdLikeKey(k));
      const preferred = preferredBarKeys.find(k => candidateNumKeys.includes(k));
      if (preferred) return preferred;

      const candidates = candidateNumKeys.length > 0 ? candidateNumKeys : numKeys;
      let bestKey = candidates[0];
      let bestRange = -1;

      for (const k of candidates) {
        const values = data.map(row => row?.[k]).filter(isFiniteNumber);
        if (values.length === 0) continue;
        const range = Math.max(...values) - Math.min(...values);
        if (range > bestRange) {
          bestRange = range;
          bestKey = k;
        }
      }
      return bestKey;
    };

    if (numKeys.length >= 1 && stringKeys.length >= 1) {
      const xAxisKey = pickXAxisKey();
      const barKey = pickBarKey();

      const formatLabel = (str) => {
        if (!str) return '';
        return str.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      };

      const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
          return (
            <div className="bg-white p-3 border border-indigo-100 shadow-xl rounded-lg text-sm">
              <p className="font-semibold text-indigo-900 mb-1">{label}</p>
              <p className="text-indigo-600">
                <span className="font-medium">{formatLabel(barKey)}:</span> {payload[0].value.toLocaleString()}
              </p>
            </div>
          );
        }
        return null;
      };

      return (
        <div className="mt-5 bg-gradient-to-br from-white to-gray-50 p-5 rounded-2xl shadow-sm border border-indigo-50/50">
          <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4 flex justify-between">
            <span>{formatLabel(barKey)} by {formatLabel(xAxisKey)}</span>
            <LineChart className="w-4 h-4 text-indigo-400" />
          </h4>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis 
                  dataKey={xAxisKey} 
                  interval={0} 
                  angle={-20} 
                  textAnchor="end" 
                  height={60} 
                  tick={{fill: '#6b7280', fontSize: 12}}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis 
                  tick={{fill: '#6b7280', fontSize: 12}}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => value >= 1000 ? `${(value/1000).toFixed(1)}k` : value}
                />
                <Tooltip content={<CustomTooltip />} cursor={{fill: '#f3f4f6'}} />
                <Bar 
                  dataKey={barKey} 
                  fill="url(#colorIndigo)" 
                  radius={[6, 6, 0, 0]} 
                  animationDuration={1500}
                >
                </Bar>
                <defs>
                  <linearGradient id="colorIndigo" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.9}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.4}/>
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans selection:bg-indigo-100 selection:text-indigo-900">
      
      {/* Left Sidebar - Chat */}
      <div className="w-2/3 flex flex-col h-full bg-white relative z-10 shadow-[4px_0_24px_rgba(0,0,0,0.02)] border-r border-gray-100">
        
        {/* Header */}
        <div className="px-6 py-5 bg-white/80 backdrop-blur-md border-b border-gray-100 flex items-center sticky top-0 z-20">
          <div className="bg-indigo-600 p-2 rounded-xl mr-3 shadow-lg shadow-indigo-200">
            <MessageSquare className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-xl text-gray-900 tracking-tight">InsightForge</h1>
            <p className="text-xs font-medium text-indigo-500 uppercase tracking-wider">AI Analytics Assistant</p>
          </div>
        </div>

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8 scroll-smooth px-8 lg:px-12 bg-slate-50/30">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              
              {/* Bot Avatar */}
              {msg.role === 'ai' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mr-4 mt-1 shadow-md">
                  <MessageSquare className="w-4 h-4 text-white" />
                </div>
              )}

              <div className={`relative px-6 py-5 ${
                msg.role === 'user' 
                  ? 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-3xl rounded-br-sm shadow-md max-w-[80%]' 
                  : 'bg-white text-gray-800 rounded-3xl rounded-tl-sm ring-1 ring-gray-900/5 shadow-sm max-w-[90%] xl:max-w-[85%]'
              }`}>
                <div className="prose prose-sm sm:prose-base prose-indigo max-w-none">
                  <p className="whitespace-pre-wrap leading-relaxed text-[15px]">{msg.content}</p>
                </div>
                
                {/* Inline Traces & Charts for AI responses */}
                {msg.role === 'ai' && msg.traces && msg.traces.length > 0 && (
                  <div className="mt-6 pt-5 border-t border-gray-100/80">
                    <div className="flex items-center space-x-2 mb-4">
                      <div className="flex-1 h-px bg-gray-100"></div>
                      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Sources & Traces</p>
                      <div className="flex-1 h-px bg-gray-100"></div>
                    </div>

                    <div className="flex flex-wrap gap-2 mb-2">
                      {Object.entries(
                        msg.traces.reduce((acc, trace) => {
                          const toolName = trace?.tool || 'Tool';
                          acc[toolName] = (acc[toolName] || 0) + 1;
                          return acc;
                        }, {})
                      ).map(([toolName, count]) => (
                        <span key={toolName} className="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                          {toolName === 'SQL Database' ? <Database className="w-3.5 h-3.5 mr-1.5 text-indigo-500" /> : <FileText className="w-3.5 h-3.5 mr-1.5 text-rose-500" />}
                          {toolName} {count > 1 && <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-white text-slate-500 shadow-sm border border-slate-200">{count}</span>}
                        </span>
                      ))}
                    </div>
                    
                    {msg.traces.map((trace, tIdx) => (
                      <div key={`chart-${tIdx}`}>
                        {trace.tool === 'SQL Database' && renderChart(trace)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mr-4 shadow-md">
                <MessageSquare className="w-4 h-4 text-white" />
              </div>
              <div className="bg-white px-5 py-4 rounded-3xl rounded-tl-sm ring-1 ring-gray-900/5 shadow-sm flex items-center space-x-2 w-fit">
                <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
              </div>
            </div>
          )}
          <div ref={endOfMessagesRef} />
        </div>

        {/* Input Area */}
        <div className="p-6 bg-white border-t border-gray-100">
          <form onSubmit={handleSend} className="relative shadow-sm rounded-2xl">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about revenue, specific campaigns, or regional trends..."
              className="w-full pl-6 pr-14 py-4 bg-gray-50 border-0 ring-1 ring-gray-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all shadow-inner text-gray-700"
              disabled={isLoading}
            />
            <button 
              type="submit" 
              className={`absolute right-2 top-2 bottom-2 p-2 rounded-xl transition-all ${
                input.trim() ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md hover:shadow-lg hover:-translate-y-0.5' : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}
              disabled={!input.trim() || isLoading}
            >
              <Send className="w-5 h-5" />
            </button>
          </form>
        </div>
      </div>

      {/* Right Sidebar - Insights & Trace Panel */}
      <div className="w-1/3 bg-slate-50 flex flex-col h-full border-l border-gray-100">
        <div className="p-6 bg-white/50 backdrop-blur-sm border-b border-gray-200 flex items-center">
          <div className="bg-emerald-100 p-2 rounded-lg mr-3 text-emerald-600">
            <LineChart className="w-5 h-5" />
          </div>
          <h2 className="font-bold text-lg text-gray-800 tracking-tight">Security & Trace</h2>
        </div>
        
        <div className="flex-1 overflow-y-auto p-6">
          <div className="bg-white border border-gray-100 shadow-sm rounded-xl p-5 mb-6 ring-1 ring-black/5">
            <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center">
              <span className="w-1.5 h-4 bg-indigo-500 rounded-full mr-2"></span>
              Filters
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Release year</label>
                <select
                  value={yearFilter}
                  onChange={(e) => setYearFilter(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-md text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="Any">Any</option>
                  <option value="2023">2023</option>
                  <option value="2024">2024</option>
                  <option value="2025">2025</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Region</label>
                <select
                  value={regionFilter}
                  onChange={(e) => setRegionFilter(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-md text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="Any">Any</option>
                  <option value="North America">North America</option>
                  <option value="Europe">Europe</option>
                  <option value="Asia-Pacific">Asia-Pacific</option>
                  <option value="Latin America">Latin America</option>
                  <option value="Middle East">Middle East</option>
                </select>
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-3">
              These are sent to the assistant as guidance.
            </p>
          </div>

          <div className="bg-blue-50 border border-blue-100 rounded-lg p-4 mb-6">
            <h3 className="text-sm font-semibold text-blue-800 mb-1">Tool-Based Restrictions</h3>
            <p className="text-xs text-blue-600 leading-relaxed">
              The AI acts strictly through controlled backend tools: 
              <br/><br/>
              <code>query_sql_database(query)</code><br/>
              <code>search_internal_documents(keyword)</code>
            </p>
          </div>
          
          {messages.length > 1 && messages[messages.length - 1].role === 'ai' && messages[messages.length - 1].traces?.length > 0 ? (
            <div>
             <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Latest Tool Execution</h3>
             {messages[messages.length - 1].traces.map((trace, idx) => (
                <div key={idx} className="bg-gray-900 rounded-lg overflow-hidden shadow-lg mb-4">
                  <div className="bg-gray-800 px-4 py-2 border-b border-gray-700 flex justify-between items-center">
                    <span className="text-xs font-mono text-gray-300">{trace.tool}</span>
                  </div>
                  <div className="p-4">
                    <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap break-all mb-4">
                      {trace.query}
                    </pre>
                    <div className="border-t border-gray-700 pt-4">
                      <p className="text-xs text-gray-500 mb-2 font-mono">Returned Payload:</p>
                      <pre className="text-xs font-mono text-blue-300 overflow-x-auto max-h-40 overflow-y-auto w-full block">
                        {JSON.stringify(trace.result, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
             ))}
            </div>
          ) : (
            <div className="text-center text-sm text-gray-400 mt-10">
              <Database className="w-8 h-8 mx-auto mb-2 opacity-20" />
              Submit a prompt to view data traces.
            </div>
          )}
        </div>
      </div>
      
    </div>
  );
}

export default App;