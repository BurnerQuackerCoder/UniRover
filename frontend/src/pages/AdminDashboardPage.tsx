import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import LiveMap from '../components/LiveMap';

interface AdminDelivery {
  id: number;
  item: string;
  destination: string;
  status: 'Pending' | 'Scheduled' | 'In Progress' | 'Awaiting Pickup' | 'Delivered' | 'Failed';
  created_at: string;
  owner: { email: string; };
}

// Reusing the same status class helper
const getStatusClass = (status: AdminDelivery['status']) => {
  switch (status) {
    case 'Delivered': return 'bg-green-200 text-green-800';
    case 'In Progress': return 'bg-blue-200 text-blue-800';
    case 'Awaiting Pickup': return 'bg-yellow-200 text-yellow-800 animate-pulse';
    case 'Scheduled': return 'bg-indigo-200 text-indigo-800';
    case 'Failed': return 'bg-red-200 text-red-800';
    default: return 'bg-gray-200 text-gray-800';
  }
};

const AdminDashboardPage = () => {
  const [deliveries, setDeliveries] = useState<AdminDelivery[]>([]);
  const [error, setError] = useState('');

  const fetchAllDeliveries = async () => {
    try {
      const response = await axiosClient.get('/admin/deliveries');
      setDeliveries(response.data);
    } catch (err) {
      setError('Failed to fetch deliveries.');
      console.error(err);
    }
  };
  
  // Use polling to get live updates every 5 seconds
  useEffect(() => {
    fetchAllDeliveries();
    const interval = setInterval(fetchAllDeliveries, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleReturnToBase = async () => {
    if (window.confirm("Are you sure you want to abort the current tour and send the robot to its base station?")) {
      try {
        await axiosClient.post('/admin/robot/return_to_base');
        alert('Return to Base command sent successfully.');
        fetchAllDeliveries(); // Refresh list immediately
      } catch (err) {
        alert('Failed to send Return to Base command.');
        console.error(err);
      }
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Admin Dashboard: All Deliveries</h1>
        <button onClick={handleReturnToBase} className="px-4 py-2 font-bold text-white bg-red-600 rounded-md hover:bg-red-700 shadow-lg">
          EMERGENCY: RETURN TO BASE
        </button>
      </div>
      <LiveMap />
      

      <div className="p-6 bg-white rounded-lg shadow-md overflow-x-auto">
        {error && <p className="text-red-500">{error}</p>}
        <table className="min-w-full bg-white">
          <thead className="bg-gray-100">
            <tr>
              <th className="py-3 px-4 text-left">Item</th>
              <th className="py-3 px-4 text-left">Destination</th>
              <th className="py-3 px-4 text-left">Requested By</th>
              <th className="py-3 px-4 text-left">Date</th>
              <th className="py-3 px-4 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {deliveries.map((delivery) => (
              <tr key={delivery.id} className="border-b hover:bg-gray-50">
                <td className="py-3 px-4">{delivery.item}</td>
                <td className="py-3 px-4">{delivery.destination}</td>
                <td className="py-3 px-4">{delivery.owner.email}</td>
                <td className="py-3 px-4">{new Date(delivery.created_at).toLocaleDateString()}</td>
                <td className="py-3 px-4">
                  <span className={`px-3 py-1 text-sm font-semibold rounded-full ${getStatusClass(delivery.status)}`}>
                    {delivery.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AdminDashboardPage;