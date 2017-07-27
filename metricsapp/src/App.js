/* This Source Code Form is subject to the terms of the Mozilla Public
   License, v. 2.0. If a copy of the MPL was not distributed with this
   file, you can obtain one at http://mozilla.org/MPL/2.0/. */

import React, { Component } from 'react'
import { Line } from 'react-chartjs-2'
import './App.css'

const DEFAULTINTERVAL = parseInt(
  localStorage.getItem('intervalSeconds') || '5',
  10
)

class App extends Component {
  state = {
    intervalSeconds: DEFAULTINTERVAL,
    paused: false,
  }
  resume = () => {
    this.setState({paused: false})
  }
  render() {
    return (
      <div className="App">
        <div className="App-header">
          <h2>Symbolication Metrics App</h2>
          <form>
            <div style={{opacity: this.state.paused ? 0.1 : 1.0}}>
              Interval:{' '}
              <input
                disabled={this.state.paused}
                style={{width: 40, fontSize: '150%'}}
                type="number"
                size={2}
                min="1"
                value={this.state.intervalSeconds}
                onChange={e => {
                  let interval = parseInt(e.target.value, 10)
                  if (isNaN(interval)) {
                    this.setState({intervalSeconds: DEFAULTINTERVAL})
                  } else {
                    localStorage.setItem('intervalSeconds', interval)
                    this.setState({intervalSeconds: interval})
                  }
                }}
              />
            </div>
            <br/>
            <button type="button" onClick={e => {
              this.setState({paused: !this.state.paused})
            }}>{this.state.paused ? 'Resume' : 'Pause'}</button>
            <button type="button" onClick={e => {
              document.location.reload()
            }}>Reset</button>
          </form>
        </div>
        {/* Send all of this's state as props. Lazy. */}
        <MetricsLines
          {...this.state}
          resume={this.resume}
        />
      </div>
    )
  }
}

export default App


function humanFileSize(size, decimals = 1) {
    var i = Math.floor( Math.log(size) / Math.log(1024) );
    return ( size / Math.pow(1024, i) ).toFixed(decimals) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i];
};


class MetricsLines extends Component {
  state = {
    serverError: null,
    stored: 0,
    retrieved: 0,
    hitRatio: {
      labels: [],
      datasets: [
        {
          label: 'Hit Ratio',
          fill: false,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(16, 80, 30, 1)'
        },
      ]
    },
    evictions: {
    labels: [],
      datasets: [
        {
          fill: false,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(34, 59, 222, 1)'
        },
      ]
    },
    keys: {
      labels: [],
      datasets: [
        {
          fill: false,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(122, 20, 139, 1)'
        },
      ]
    },
    hits: {
      labels: [],
      datasets: [
        {
          label: 'Hits',
          fill: false,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(15, 200, 56, 1)'
        },
        {
          label: 'Misses',
          fill: false,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(238, 50, 50, 1)'
        },
      ]
    },
    maxmemory: {
      labels: [],
      datasets: [
        {
          label: 'Max Memory',
          fill: false,
          pointRadius: 2,
          lineWidth: 2,
          data: [],
          backgroundColor: 'rgba(0, 86, 108, 1)'
        },
        {
          label: 'Used Memory',
          fill: true,
          pointRadius: 2,
          data: [],
          backgroundColor: 'rgba(22, 149, 196, 1)'
        },

      ]
    },
  }

  componentDidMount() {
    this.runLoop()
  }

  runLoop() {
    if (!this.props.paused && !this.state.serverError) {
      this.fetchDataPoints()
    }
    this.loop = setTimeout(() => {
      this.runLoop()
    }, this.props.intervalSeconds * 1000)
  }

  async fetchDataPoints() {

    try {
      let response = await fetch('/symbolicate/metrics')
      if (response.status !== 200) {
        this.setState({
          serverError: {
            status: response.status,
            statusText: response.statusText,
          }
        })
        return
      }
      let data = await response.json()
      this.setState(prevState => {
        let lastLabel = 0
        if (prevState.hits.labels.length) {
          lastLabel = prevState.hits.labels[prevState.hits.labels.length - 1]
        }
        let labels = [...prevState.hits.labels, lastLabel + this.props.intervalSeconds]

        const pointsCount = prevState.hits.datasets[0].data.length
        let pointRadius = 5
        if (pointsCount > 100) pointRadius = 1
        else if (pointsCount > 30) pointRadius = 2
        else if (pointsCount > 15) pointRadius = 3
        else if (pointsCount > 5) pointRadius = 4

        return {
          stored: data.stored,
          retrieved: data.retrieved,
          hits: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.hits.datasets[0].data, data.hits],
                pointRadius: pointRadius,
              },
              {
                data: [...prevState.hits.datasets[1].data, data.misses],
                pointRadius: pointRadius,
              },
            ]
          },
          maxmemory: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.maxmemory.datasets[0].data, data.maxmemory.bytes],
                pointRadius: pointRadius,
              },
              {
                data: [...prevState.maxmemory.datasets[1].data, data.used_memory.bytes],
                pointRadius: pointRadius,
              },
            ]
          },
          hitRatio: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.hitRatio.datasets[0].data, data.percent_of_hits],
                pointRadius: pointRadius,
              },
            ]
          },
          keys: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.keys.datasets[0].data, data.keys],
                pointRadius: pointRadius,
              },
            ]
          },
        }
      })
    } catch (err) {
      console.error(err);
    }
  }

  baseOptions = {
    legend: {
      display: false,
    },
    scales: {
      xAxes: [{
        display: false,
      }]
    }
  }

  hitsOptions = Object.assign({}, this.baseOptions, {
    legend: {
      display: true,
    },
  })

  hitRatioOptions = Object.assign({}, this.baseOptions, {
    scales: {
      xAxes: [{
        display: false,
      }],
      yAxes: [{
        ticks: {
          callback: (v) => {
            if (v === 0) {
              return '0%'
            }
            return v.toFixed(0) + '%'
          },
        },

      }]
    }
  })

  maxmemoryOptions = Object.assign({}, this.hitsOptions, {
    scales: {
      xAxes: [{
        display: false,
      }],
      yAxes: [{
        ticks: {
          callback: (v) => {
            if (v === 0) {
              return "0"
            }
            return humanFileSize(v)
          },
        },

      }]
    }
  })

  tryAgain = event => {
    event.preventDefault()
    this.setState({serverError: null})
    this.props.resume()
  }

  render() {
    return <div className="metricslines">
      {
        this.state.serverError ?
        <ShowServerError
          {...this.state.serverError}
          tryAgain={this.tryAgain}/>
        : null
      }
      <div className="metricsline">
        <h3 className="title">Hits and Misses</h3>
        <Line
          data={this.state.hits}
          options={this.hitsOptions}/>
      </div>
      <div className="metricsline">
        <h3 className="title">Hit Ratio</h3>
        <Line
          data={this.state.hitRatio}
          options={this.hitRatioOptions}/>
      </div>
      <div className="metricsline">
        <h3 className="title">Keys</h3>
        <Line
          data={this.state.keys}
          options={this.baseOptions}/>
      </div>
      <div className="metricsline">
        <h3 className="title">Max Memory</h3>
        <Line
          data={this.state.maxmemory}
          options={this.maxmemoryOptions}/>
      </div>
      <div className="metricsline">
        <h3 className="title">Storage</h3>
        <Number
          number={this.state.stored}/>
        <small>Total amount of data written to the LRU cache</small>
        <h3 className="title">Retrieved</h3>
        <Number
          number={this.state.retrieved}/>
        <small>Total amount of data extracted out of the LRU cache</small>
      </div>
    </div>
  }
}


const ShowServerError = ({ status, statusText, tryAgain }) => {
  return <div className="server-error">
    <h2>Server Error</h2>
    <p>Unable to talk to the server for metrics data</p>
    <code>{status}</code>
    <code>{statusText}</code>

    <p>
      Perhaps
      <button type="button" onClick={e => document.location.reload(true)}>Reload</button>
      <button type="button" onClick={tryAgain}>Try Again</button>
    </p>
  </div>
}


const Number = ({ number }) => {
  return <h1 className="number" title={`${number} bytes`}>{humanFileSize(number)}</h1>
}
