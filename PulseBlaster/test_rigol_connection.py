"""
RIGOL DSG836 Connection Diagnostic Tool
--------------------------------------
This script tests different connection parameters to help diagnose
communication issues with the RIGOL DSG836 signal generator.
"""

import socket
import time

def test_connection(ip_address, port, timeout=5.0):
    """Test basic TCP connection to RIGOL DSG836."""
    print(f"Testing connection to {ip_address}:{port} (timeout: {timeout}s)")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip_address, port))
        print("✅ TCP connection successful")
        
        # Try to send *IDN? command
        try:
            command = "*IDN?\n"
            sock.send(command.encode('utf-8'))
            print(f"📤 Sent: {command.strip()}")
            
            # Wait for response
            time.sleep(0.1)
            response = sock.recv(1024).decode('utf-8')
            print(f"📥 Received: {repr(response)}")
            
            if response.strip():
                print("✅ Instrument responded")
                return True, response.strip()
            else:
                print("❌ No response received")
                return False, "No response"
                
        except Exception as e:
            print(f"❌ Command failed: {e}")
            return False, str(e)
        finally:
            sock.close()
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False, str(e)

def test_multiple_ports(ip_address):
    """Test common ports used by RIGOL instruments."""
    common_ports = [5555, 5025, 111, 502, 23]  # Common SCPI/instrument ports
    
    print(f"\n🔍 Testing multiple ports for {ip_address}:")
    print("-" * 50)
    
    for port in common_ports:
        success, response = test_connection(ip_address, port, timeout=3.0)
        if success:
            print(f"🎯 Working port found: {port}")
            print(f"   Response: {response}")
            return port
        print()
    
    print("❌ No working ports found")
    return None

def test_different_commands(ip_address, port=5555):
    """Test different identification commands."""
    commands = [
        "*IDN?",
        "*IDN?\n", 
        "*IDN?\r\n",
        "IDN?",
        ":SYST:IDN?",
        ":SYSTEM:IDENTIFY?"
    ]
    
    print(f"\n🧪 Testing different commands on {ip_address}:{port}:")
    print("-" * 50)
    
    for cmd in commands:
        print(f"Testing: {repr(cmd)}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ip_address, port))
            
            sock.send(cmd.encode('utf-8'))
            time.sleep(0.2)
            
            response = sock.recv(1024).decode('utf-8')
            print(f"  Response: {repr(response)}")
            
            if response.strip() and "error" not in response.lower():
                print(f"  ✅ Success with: {repr(cmd)}")
            else:
                print(f"  ❌ Failed or error response")
                
            sock.close()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
        
        print()

def ping_test(ip_address):
    """Test if the IP address is reachable."""
    import subprocess
    import platform
    
    print(f"🏓 Ping test for {ip_address}:")
    
    # Use appropriate ping command for Windows
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "4", ip_address]
    else:
        cmd = ["ping", "-c", "4", ip_address]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ IP address is reachable")
            return True
        else:
            print("❌ IP address is not reachable")
            print(result.stdout)
            return False
    except Exception as e:
        print(f"❌ Ping failed: {e}")
        return False

def main():
    """Main diagnostic function."""
    ip_address = "192.168.0.222"  # Your RIGOL DSG836 IP
    
    print("🔧 RIGOL DSG836 Connection Diagnostic Tool")
    print("=" * 50)
    
    # Step 1: Ping test
    print("\n1. Network Connectivity Test")
    ping_ok = ping_test(ip_address)
    
    if not ping_ok:
        print("⚠️  Network connectivity issue detected!")
        print("   Please check:")
        print("   - Is the instrument powered on?")
        print("   - Is the Ethernet cable connected?")
        print("   - Is the IP address correct?")
        print("   - Are both devices on the same network?")
        return
    
    # Step 2: Port scanning
    print("\n2. Port Discovery")
    working_port = test_multiple_ports(ip_address)
    
    if working_port:
        print(f"\n3. Command Testing (Port {working_port})")
        test_different_commands(ip_address, working_port)
    else:
        print("\n⚠️  No working ports found!")
        print("   Please check:")
        print("   - Is the LAN/Remote interface enabled on the instrument?")
        print("   - Check the instrument's network settings menu")
        print("   - Try connecting via USB or serial first to configure network")
    
    print("\n" + "=" * 50)
    print("📋 Diagnostic Complete!")
    
    if working_port:
        print(f"✅ Recommended settings:")
        print(f"   IP: {ip_address}")
        print(f"   Port: {working_port}")
        print("   Update your PulseBlaster code with these settings.")
    else:
        print("❌ Connection issues detected. Please check instrument settings.")

if __name__ == "__main__":
    main() 