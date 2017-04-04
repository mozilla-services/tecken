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
        <MetricsLines {...this.state}/>
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

        return {
          hits: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.hits.datasets[0].data, data.hits],
              },
              {
                data: [...prevState.hits.datasets[1].data, data.misses],
              },
            ]
          },
          maxmemory: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.maxmemory.datasets[0].data, data.maxmemory.bytes],
              },
              {
                data: [...prevState.maxmemory.datasets[1].data, data.used_memory.bytes],
              },
            ]
          },
          hitRatio: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.hitRatio.datasets[0].data, data.percent_of_hits],
              },
            ]
          },
          evictions: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.evictions.datasets[0].data, data.evictions],
              },
            ]
          },
          keys: {
            labels: labels,
            datasets: [
              {
                data: [...prevState.keys.datasets[0].data, data.keys],
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

  render() {
    return <div className="metricslines">
      {
        this.state.serverError ?
        <ShowServerError {...this.state.server}/> : null
      }
      <div className="metricsline">
        <h3>Hits and Misses</h3>
        <Line
          data={this.state.hits}
          options={this.hitsOptions}/>
      </div>
      <div className="metricsline">
        <h3>Hit Ratio</h3>
        <Line
          data={this.state.hitRatio}
          options={this.hitRatioOptions}/>
      </div>
      <div className="metricsline">
        <h3>Evictions</h3>
        <Line
          data={this.state.evictions}
          options={this.baseOptions}/>
      </div>
      <div className="metricsline">
        <h3>Keys</h3>
        <Line
          data={this.state.keys}
          options={this.baseOptions}/>
      </div>
      <div className="metricsline">
        <h3>Max Memory</h3>
        <Line
          data={this.state.maxmemory}
          options={this.maxmemoryOptions}/>
      </div>
    </div>
  }
}


const ShowServerError = ({ status, statusText }) => {
  return <div className="server-error">
    <h2>Server Error</h2>
    <p>Unable to talk to the server for metrics data</p>
    <code>{status}</code>
    <code>{statusText}</code>

    <p>
      Perhaps
      <button type="button" onClick={e => document.location.reload(true)}>Reload</button>
    </p>
  </div>
}
