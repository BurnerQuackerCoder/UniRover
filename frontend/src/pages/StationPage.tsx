import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import LiveMap from '../components/LiveMap'; // <-- 1. IMPORT THE LIVEMAP COMPONENT

// Base URL for the backend
const API_URL = 'http://localhost:8000';

// Define the type for a single delivery object
interface Delivery {
  id: number;
  item: string;
  destination: string;
  notes: string | null;
  status: 'Awaiting Pickup';
  created_at: string;
}

const StationPage = () => {
  const { destinationName } = useParams<{ destinationName: string }>();
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [error, setError] = useState('');

  // Function to fetch deliveries for this station
  const fetchDeliveries = async () => {
    if (!destinationName) return;

    try {
      const response = await axios.get(
        `${API_URL}/public/deliveries/${destinationName}`
      );
      setDeliveries(response.data);
      setError('');
    } catch (err) {
      console.error('Failed to fetch deliveries:', err);
      setError('Could not fetch deliveries.');
    }
  };

  // Poll for new deliveries every 5 seconds
  useEffect(() => {
    fetchDeliveries();
    const interval = setInterval(fetchDeliveries, 5000);
    return () => clearInterval(interval);
  }, [destinationName]);

  // Function to handle the "Confirm Pickup" button click
  const handleConfirmPickup = async (deliveryId: number) => {
    try {
      await axios.post(
        `${API_URL}/public/confirm_pickup/${deliveryId}`
      );
      fetchDeliveries();
    } catch (err) {
      console.error('Failed to confirm pickup:', err);
      alert('Failed to confirm pickup. Please try again.');
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4">
      {/* 2. MAKE THE CONTAINER WIDER */}
      <div className="w-full max-w-4xl p-8 space-y-6 bg-white rounded-lg shadow-2xl mx-auto">
        <h1 className="text-3xl font-bold text-center text-blue-600">
          Zuse-Opta Station
        </h1>
        <h2 className="text-2xl font-semibold text-center text-gray-700">
          Destination: {destinationName}
        </h2>

        {/* --- 3. ADD THE LIVEMAP COMPONENT HERE --- */}
        <div className="w-full border rounded-lg overflow-hidden shadow-inner">
          <LiveMap />
        </div>
        {/* --- END OF LIVEMAP --- */}

        <hr />

        <h3 className="text-xl font-bold text-gray-800">Awaiting Pickup</h3>
        <div className="space-y-4">
          {error && <p className="text-red-500 text-center">{error}</p>}

          {deliveries.length === 0 && (
            <p className="text-lg text-gray-500 text-center">
              (No deliveries currently awaiting pickup)
            </p>
          )}

          {deliveries.map((delivery) => (
            <div 
              key={delivery.id} 
              className="p-6 border rounded-lg shadow-md bg-blue-50 flex flex-col md:flex-row justify-between items-center space-y-4 md:space-y-0"
            >
              <div className="text-center md:text-left">
                <p className="text-xl font-bold text-gray-800">
                  Item: {delivery.item}
                </p>
                <p className="text-sm text-gray-600">
                  Notes: {delivery.notes || 'N/A'}
                </p>
              </div>
              <button
                onClick={() => handleConfirmPickup(delivery.id)}
                className="px-6 py-3 font-bold text-white bg-green-600 rounded-md hover:bg-green-700 text-lg shadow-lg"
              >
                Confirm Pickup
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default StationPage;