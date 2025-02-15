import sys
import json
import requests

from flask import Flask, request, Response
from gevent import pywsgi

import time
import qiskit
from qiskit import IBMQ
import math
import struct

import QLogicWithQiskit
from QLogicWithQiskit import QLogic

app = Flask(__name__)
_provider = None
_backend = None
_device = None
_numQubits = 0
_circuit = None
_bitCache = ''
QLogic = QLogic()

def main():
    # Commandline Arguments (IBM Q API KEY, port)
    argNo = len(sys.argv) - 1
    if argNo < 2:
        print("----------------------------------------------------------------------------------------")
        print("Please provide arguments: <port> <IBM Q API KEY> [IBM backend|empty for simulator] [num qubits]")
        print("----------------------------------------------------------------------------------------")
    else:
        # As of Nov 2021, these are the backends that were available to my API KEY
        global _device, _numQubits
        #_device = "ibmq_santiago" # 5 qubit / 32 quantum volume
        #_device = "ibmq_manila"   # 5 qubit / 32 quantum volume
        #_device = "ibmq_bogota"   # 5 qubit / 32 quantum volume
        #_device = "ibmq_quito"    # 5 qubit / 16 quantum volume
        #_device = "ibmq_belem"    # 5 qubit / 16 quantum volume
        #_device = "ibmq_lima"     # 5 qubit / 8 quantum volume
        #_device = "ibmq_armonk"   # 1 qubit / 1 quantum volume
        _device = "ibmq_qasm_simulator"
        _numQubits = 5
        port = sys.argv[1]
        api_key = sys.argv[2]
        if argNo >= 4:
            _device = sys.argv[3]
            _numQubits = int(sys.argv[4])
        ip = requests.get('https://api.ipify.org').text
        print("----------------------------------------------------------------------------------------")
        print("Serving MrBean on http://", ip, ":", port, " with IBM Q API KEY: ", api_key, " on backend device: ", _device, " with ", _numQubits, " qubits", sep='')
        print("----------------------------------------------------------------------------------------")

        # set up connection to an IBM quantum computer
        IBMQ.save_account(api_key) # here you should put the api token from your IBM Quantum account
        IBMQ.load_account()
        global _provider, _backend
        _provider = IBMQ.get_provider('ibm-q')
        _backend = _provider.get_backend(_device) # this can be set to any computer from the list of IBM computers
        qr = qiskit.QuantumRegister(_numQubits)
        cr = qiskit.ClassicalRegister(_numQubits)

        # the quantum circuit to run jobs on, QRNG here
        global _circuit
        _circuit = qiskit.QuantumCircuit(qr, cr)
        _circuit.h(qr) # Apply Hadamard gate to qubits
        _circuit.measure(qr,cr) # Collapses qubit to either 1 or 0 w/ equal prob.
        print("Quantum H circuit set up")

        serve("MrBeanServer", port, id)

def serve(servername, port, id):

    # Strips QISKit output to just a bitstring.
    def _bit_from_counts(counts):
        return [k for k, v in counts.items() if v == 1][0]

    # Populates the bitCache with at least n more bits.
    def _request_bits(n):
        global _bitCache
        iterations = math.ceil(n/_circuit.width()*2)
        for _ in range(iterations):
            # Create new job and run the quantum circuit
            start_time = time.time()
            job = qiskit.execute(_circuit, _backend, shots=1)
            _bitCache += _bit_from_counts(job.result().get_counts())
            print("--- %s seconds for this request bit iteration ---" % (time.time() - start_time))

    # Returns a random n-bit string by popping n bits from bitCache.
    @app.route('/api/get_random_bit_string')
    def get_random_bit_string():
        len = 8
        if 'min' in request.args:
            len = float(request.args.get('len'))
        print("get_random_bit_string(", len, ")", sep='')
        response = str(_get_bit_string(len))
        print("->", response)
        return Response(response, content_type='text/plain')

    def _get_bit_string(n):
        global _bitCache
        if len(_bitCache) < n:
            _request_bits(n-len(_bitCache))
        bitString = _bitCache[0:n]
        _bitCache = _bitCache[n:]
        return bitString

    ####
    # The following getXXX random numbers were originally implemented here:
    # https://github.com/ozaner/qRNG
    # We've exposed them through our API for convenient consumption.
    ###

    # Returns a random integer between and including [min, max].
    # Running time is probabalistic but complexity is still O(n)
    @app.route('/api/get_random_int')
    def get_random_int():
        min = 0
        if 'min' in request.args:
            min = int(request.args.get('min'))
        max = 9
        if 'max' in request.args:
            max = int(request.args.get('max'))
        print("get_random_int(", min, ",", max, ")", sep='')
        delta = max-min
        n = math.floor(math.log(delta,2))+1
        result = int(_get_bit_string(n),2)
        while(result > delta):
            result = int(_get_bit_string(n),2)
        response = str(result+min)
        print("->", response)
        return Response(response, content_type='text/plain')

    # def getRandomIntEntaglement(min,max):

    # Returns a random 32 bit integer
    @app.route('/api/get_random_int32')
    def get_random_int32():
        print("get_random_int32()")
        response = (_get_random_int32())
        print("->", response)
        return Response(str(response), content_type='text/plain')

    def _get_random_int32():
        return int(_get_bit_string(32),2)

    # Returns a random 64 bit integer
    @app.route('/api/get_random_int64')
    def get_random_int64():
        print("get_random_int64()")
        response = (_get_random_int64())
        print("->", response)
        return Response(str(response), content_type='text/plain')

    def _get_random_int64():
        return int(_get_bit_string(64),2)

    # Returns a random float from a uniform distribution in the range [min, max).
    @app.route('/api/get_random_float')
    def get_random_float():
        min = 0
        if 'min' in request.args:
            min = float(request.args.get('min'))
        max = 9
        if 'max' in request.args:
            max = float(request.args.get('max'))
        print("get_random_float(", min, ",", max, ")", sep='')
        response = str(_get_random_float(min, max))
        print("->", response)
        return Response(response, content_type='text/plain')

    def _get_random_float(min, max):
        # Get random float from [0,1)
        unpacked = 0x3F800000 | _get_random_int32() >> 9
        packed = struct.pack('I',unpacked)
        value = struct.unpack('f',packed)[0] - 1.0
        response = (max-min)*value+min # Scale float to given range
        return response

    @app.route('/api/get_random_double')
    def get_random_double():
        min = 0
        if 'min' in request.args:
            min = float(request.args.get('min'))
        max = 9
        if 'max' in request.args:
            max = float(request.args.get('max'))
        print("get_random_double(", min, ",", max, ")", sep='')
        response = str(_get_random_double(min, max))
        print("->", response)
        return Response(response, content_type='text/plain')

    def _get_random_double(min, max):
        # Get random double from [0,1)
        unpacked = 0x3FF0000000000000 | _get_random_int64() >> 12
        packed = struct.pack('Q',unpacked)
        value = struct.unpack('d',packed)[0] - 1.0
        response = (max-min)*value+min # Scale double to given range
        return response

    # Returns a random complex with both real and imaginary parts
    # from the given ranges. If no imaginary range specified, real range used.
    @app.route('/api/get_random_complex_rect')
    def get_random_complex_rect():
        r1 = 0
        if 'r1' in request.args:
            r1 = float(request.args.get('r1'))
        r2 = 4 # 適当な数字
        if 'r2' in request.args:
            r2 = float(request.args.get('r2'))
        i1 = None
        if 'i1' in request.args:
            i1 = float(request.args.get('i1'))
        i2 = None
        if 'i2' in request.args:
            i2 = int(request.args.get('i2'))
        print("get_random_complex_rect(", r1, ",", r2, ",", i1, ",", i2, ")", sep='')
        re = _get_random_float(r1,r2)
        if i1 == None or i2 == None:
            im = _get_random_float(r1,r2)
        else:
            im = _get_random_float(i1,i2)
        response = str(re+im*1j)
        print("->", response)
        return Response(response, content_type='text/plain')

    # Returns a random complex in rectangular form from a given polar range.
    # If no max angle given, [0,2pi) used.
    @app.route('/api/get_random_complex_polar')
    def get_random_complex_polar():
        r = 0
        if 'r' in request.args:
            r = float(request.args.get('r'))
        theta=2*math.pi
        if 'theta' in request.args:
            theta = float(request.args.get('theta'))
        print("get_random_complex_polar(", r, ",", theta, ")", sep='')
        r0 = r * math.sqrt(_get_random_float(0,1))
        theta0 = _get_random_float(0,theta)
        response = str(r0*math.cos(theta0)+r0*math.sin(theta0)*1j)
        return Response(response, content_type='text/plain')

    ####
    # The following expose the QLogic functions in QLogicWithQiskit.py (Backend.py as given by Kartikeya) as API calls
    ###

    @app.route('/api/qlogic/begin_play_non_statevector')
    def begin_play_non_statevector():
        # TODO: this approach is a work in progress, not usable at the moment
        print("QLogic begin_play_non_statevector()")
        # can't call collapse if playing with this circuit coz can't use qasm_simulator or ibmq_*** real devices as used for the RNG coz they don't have a statevector
        QLogicWithQiskit.set_backend(_backend)
        response = QLogic.begin_play()
        return Response(json.dumps({"result": "ok"}), content_type='text/json; charset="utf-8"')

    @app.route('/api/qlogic/begin_play')
    def begin_play():
        print("QLogic begin_play()")
        response = QLogic.begin_play()
        return Response(json.dumps({"result": "ok"}), content_type='text/json; charset="utf-8"')
    
    @app.route('/api/qlogic/init')
    def init():
        print("QLogic init()")
        response = QLogic.init()
        return Response(json.dumps({"result": "ok"}), content_type='text/json; charset="utf-8"')

    @app.route('/api/qlogic/collapse')
    def collapse():
        print("QLogic collapse()")
        response = QLogic.collapse()
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/get_probv')
    def get_probv():
        print("QLogic get_probv()")
        response = json.dumps({"result": QLogic.get_probv()})
        print(response)
        return Response(response, content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/reset0')
    def reset0():
        print("QLogic reset0()")
        response = QLogic.reset0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/reset1')
    def reset1():
        print("QLogic reset1()")
        response = QLogic.reset1()
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/X0')
    def X0():
        print("QLogic X0()")
        response = QLogic.X0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/H0')
    def H0():
        print("QLogic H0()")
        response = QLogic.H0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/Y0')
    def Y0():
        print("QLogic Y0()")
        response = QLogic.Y0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/Z0')
    def Z0():
        print("QLogic Z0()")
        response = QLogic.Z0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/S0')
    def S0():
        print("QLogic S0()")
        response = QLogic.S0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/CNOT0')
    def CNOT0():
        print("QLogic CNOT0()")
        response = QLogic.CNOT0()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/X1')
    def X1():
        print("QLogic X1()")
        response = QLogic.X1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/H1')
    def H1():
        print("QLogic H1()")
        response = QLogic.H1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/Y1')
    def Y1():
        print("QLogic Y1()")
        response = QLogic.Y1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/Z1')
    def Z1():
        print("QLogic Z1()")
        response = QLogic.Z1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/S1')
    def S1():
        print("QLogic S1()")
        response = QLogic.S1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    @app.route('/api/qlogic/CNOT1')
    def CNOT1():
        print("QLogic CNOT1()")
        response = QLogic.CNOT1()
        print(str(response))
        return Response(str(response), content_type='text/plain; charset="utf-8"')

    # Get the status of the API server
    @app.route('/api/status')
    def status():
        response = json.dumps({"server" : servername, "status": "online", "qubits": _numQubits, "device": _device})
        print("/status")
        print("->", response)
        return Response(response, status=200, content_type='text/plain')

    server = pywsgi.WSGIServer(('0.0.0.0', int(port)), application=app)
    server.serve_forever()

if __name__ == "__main__":
    main()