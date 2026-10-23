import React, { useState } from 'react';
import { Layout, PageId } from '../components/Layout';
import Overview from '../pages/Overview';
import LiveRecovery from '../pages/LiveRecovery';
import PaymentInvestigation from '../pages/PaymentInvestigation';
import Experiments from '../pages/Experiments';
import AIIntelligence from '../pages/AIIntelligence';
import Policies from '../pages/Policies';
import SystemHealth from '../pages/SystemHealth';
import AuditLog from '../pages/AuditLog';
import AuditSearchPage from '../pages/AuditSearchPage';

export const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageId>('overview');

  const renderPage = () => {
    switch (currentPage) {
      case 'overview':
        return <Overview />;
      case 'live-recovery':
        return <LiveRecovery />;
      case 'payments':
        return <PaymentInvestigation />;
      case 'experiments':
        return <Experiments />;
      case 'ai-decisions':
        return <AIIntelligence />;
      case 'policies':
        return <Policies />;
      case 'system-health':
        return <SystemHealth />;
      case 'audit-log':
        return <AuditLog />;
      case 'audit-search':
        return <AuditSearchPage />;
      default:
        return <Overview />;
    }
  };

  return (
    <Layout currentPage={currentPage} setCurrentPage={setCurrentPage}>
      {renderPage()}
    </Layout>
  );
};

export default App;
