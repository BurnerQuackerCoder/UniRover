import axios from 'axios';

const axiosClient = axios.create({
  baseURL: 'http://localhost:8000', // Your FastAPI backend URL
});

// Interceptor to add the auth token to every request if it exists
axiosClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export default axiosClient;