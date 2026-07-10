/**
 * frontend/src/api-real.ts
 * Real API Client - Connect to actual backend
 * Production-ready API integration
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

interface Position {
  id: number;
  symbol: string;
  position_type: 'buy' | 'sell';
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  profit: number;
  pnl_percent: number;
  status: 'open' | 'closed' | 'pending';
}

interface Trade {
  id: number;
  symbol: string;
  entry_price: number;
  exit_price: number;
  volume: number;
  profit_loss: number;
  pnl_percent: number;
  status: 'open' | 'closed' | 'cancelled';
  entry_time: string;
  exit_time?: string;
  strategy: string;
}

interface Alert {
  id: number;
  alert_type: string;
  level: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

/**
 * API Client Class
 * Handles all communication with backend
 */
class ApiClient {
  private client: AxiosInstance;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add request interceptor for auth
    this.client.interceptors.request.use(
      (config) => {
        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Token expired, try to refresh
          if (this.refreshToken) {
            try {
              await this.refreshAccessToken();
              // Retry original request
              return this.client.request(error.config!);
            } catch (refreshError) {
              // Refresh failed, redirect to login
              this.handleLogout();
            }
          }
        }
        return Promise.reject(error);
      }
    );

    // Load tokens from localStorage
    this.loadTokens();
  }

  private loadTokens() {
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }

  private saveTokens(accessToken: string, refreshToken: string) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
  }

  private handleLogout() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  }

  /**
   * Authentication Endpoints
   */

  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await this.client.post<ApiResponse<AuthResponse>>(
      '/auth/login',
      { username, password }
    );
    
    if (response.data.data) {
      const { access_token, refresh_token } = response.data.data;
      this.saveTokens(access_token, refresh_token);
      return response.data.data;
    }
    
    throw new Error(response.data.error || 'Login failed');
  }

  async logout(): Promise<void> {
    try {
      await this.client.post('/auth/logout');
    } finally {
      this.handleLogout();
    }
  }

  private async refreshAccessToken(): Promise<void> {
    const response = await this.client.post<ApiResponse<AuthResponse>>(
      '/auth/refresh',
      { refresh_token: this.refreshToken }
    );
    
    if (response.data.data) {
      const { access_token, refresh_token } = response.data.data;
      this.saveTokens(access_token, refresh_token);
    }
  }

  /**
   * Positions Endpoints
   */

  async getPositions(): Promise<Position[]> {
    const response = await this.client.get<ApiResponse<Position[]>>(
      '/trading/positions'
    );
    return response.data.data || [];
  }

  async getPosition(id: number): Promise<Position> {
    const response = await this.client.get<ApiResponse<Position>>(
      `/trading/positions/${id}`
    );
    
    if (!response.data.data) {
      throw new Error('Position not found');
    }
    
    return response.data.data;
  }

  async closePosition(id: number): Promise<Position> {
    const response = await this.client.post<ApiResponse<Position>>(
      `/trading/positions/${id}/close`
    );
    
    if (!response.data.data) {
      throw new Error('Failed to close position');
    }
    
    return response.data.data;
  }

  /**
   * Trades Endpoints
   */

  async getTrades(limit: number = 50): Promise<Trade[]> {
    const response = await this.client.get<ApiResponse<Trade[]>>(
      '/trading/trades',
      { params: { limit } }
    );
    return response.data.data || [];
  }

  async getTradeHistory(symbol?: string, limit: number = 100): Promise<Trade[]> {
    const response = await this.client.get<ApiResponse<Trade[]>>(
      '/trading/trades/history',
      { params: { symbol, limit } }
    );
    return response.data.data || [];
  }

  /**
   * Alerts Endpoints
   */

  async getAlerts(unread_only: boolean = false): Promise<Alert[]> {
    const response = await this.client.get<ApiResponse<Alert[]>>(
      '/alerts',
      { params: { unread_only } }
    );
    return response.data.data || [];
  }

  async markAlertAsRead(id: number): Promise<Alert> {
    const response = await this.client.post<ApiResponse<Alert>>(
      `/alerts/${id}/read`
    );
    
    if (!response.data.data) {
      throw new Error('Failed to mark alert as read');
    }
    
    return response.data.data;
  }

  /**
   * Analytics Endpoints
   */

  async getPortfolioStats() {
    const response = await this.client.get(
      '/analytics/portfolio'
    );
    return response.data.data;
  }

  async getTradeStats(period: string = '30d') {
    const response = await this.client.get(
      '/analytics/trades',
      { params: { period } }
    );
    return response.data.data;
  }

  async getPnLChart(period: string = '30d') {
    const response = await this.client.get(
      '/analytics/pnl',
      { params: { period } }
    );
    return response.data.data;
  }

  /**
   * Health Check
   */

  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health');
      return response.status === 200;
    } catch {
      return false;
    }
  }
}

// Export singleton instance
export const apiClient = new ApiClient();

// Export types
export type { Position, Trade, Alert, User, AuthResponse };
