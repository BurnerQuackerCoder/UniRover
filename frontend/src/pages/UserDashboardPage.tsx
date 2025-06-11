import { useState, useEffect, FormEvent } from 'react';
import axiosClient from '../api/axiosClient';

interface Delivery {
  id: number;
  item: string;
  destination: string;
  notes: string | null;
  status: 'Pending' | 'Scheduled' | 'In Progress' | 'Awaiting Pickup' | 'Delivered' | 'Failed';
  created_at: string;
}

// Helper to get color styles for different statuses
const getStatusClass = (status: Delivery['status']) => {
  switch (status) {
    case 'Delivered': return 'bg-green-200 text-green-800';
    case 'In Progress': return 'bg-blue-200 text-blue-800';
    case 'Awaiting Pickup': return 'bg-yellow-200 text-yellow-800 animate-pulse';
    case 'Scheduled': return 'bg-indigo-200 text-indigo-800';
    case 'Failed': return 'bg-red-200 text-red-800';
    default: return 'bg-gray-200 text-gray-800';
  }
};

const UserDashboardPage = () => {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [error, setError] = useState('');
  const [formState, setFormState] = useState({ item: '', destination: '', notes: '' });

  const fetchDeliveries = async () => {
    try {
      const response = await axiosClient.get('/deliveries');
      setDeliveries(response.data);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch deliveries.');
    }
  };

  // Use polling to get live updates every 5 seconds
  useEffect(() => {
    fetchDeliveries(); // Fetch immediately on component mount
    const interval = setInterval(fetchDeliveries, 5000);
    return () => clearInterval(interval); // Cleanup on component unmount
  }, []);

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormState({ ...formState, [e.target.name]: e.target.value });
  };
  
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await axiosClient.post('/deliveries', formState);
      setFormState({ item: '', destination: '', notes: '' }); // Reset form
      fetchDeliveries(); // Refresh list immediately
    } catch (err) {
      setError('Failed to create delivery request.');
      console.error(err);
    }
  };

  const handleConfirmPickup = async (deliveryId: number) => {
    try {
      await axiosClient.post(`/deliveries/${deliveryId}/confirm_pickup`);
      fetchDeliveries(); // Refresh list immediately
    } catch (err) {
      alert('Failed to confirm pickup.');
      console.error(err);
    }
  };

  return (
    <div className="space-y-8">
      {/* Create Delivery Form */}
      <div className="p-6 bg-white rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-4">Create a New Delivery Request</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Form fields... */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium">Item</label>
              <input name="item" type="text" value={formState.item} onChange={handleFormChange} required className="w-full px-3 py-2 mt-1 border rounded-md" placeholder="e.g., Documents" />
            </div>
            <div>
              <label className="block text-sm font-medium">Destination</label>
              <input name="destination" type="text" value={formState.destination} onChange={handleFormChange} required className="w-full px-3 py-2 mt-1 border rounded-md" placeholder="e.g., Room 101" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium">Notes (Optional)</label>
            <textarea name="notes" value={formState.notes} onChange={handleFormChange} className="w-full px-3 py-2 mt-1 border rounded-md" />
          </div>
          <button type="submit" className="px-4 py-2 font-bold text-white bg-blue-600 rounded-md hover:bg-blue-700">Submit Request</button>
        </form>
      </div>

      {/* Delivery List */}
      <div className="p-6 bg-white rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-4">My Delivery History</h2>
        {error && <p className="text-red-500">{error}</p>}
        {deliveries.length === 0 ? (
          <p>You have no delivery requests.</p>
        ) : (
          <ul className="space-y-4">
            {deliveries.map((delivery) => (
              <li key={delivery.id} className="p-4 border rounded-md flex justify-between items-center">
                <div>
                  <p className="font-bold">{delivery.item} to {delivery.destination}</p>
                  <p className="text-sm text-gray-500">Requested: {new Date(delivery.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className={`px-3 py-1 text-sm font-semibold rounded-full ${getStatusClass(delivery.status)}`}>
                    {delivery.status}
                  </span>
                  {delivery.status === 'Awaiting Pickup' && (
                    <button onClick={() => handleConfirmPickup(delivery.id)} className="px-4 py-2 font-bold text-white bg-green-600 rounded-md hover:bg-green-700">
                      Confirm Pickup
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default UserDashboardPage;