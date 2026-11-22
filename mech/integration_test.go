package mech

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"os"
	"testing"
)

// Exercise the actual controller, including its panic-recovery counter, against
// the organizer's recordings. Protocol validation alone cannot detect a panic
// that was converted into a legal idle action.
func fixture(t *testing.T) (Hello, []Obs) {
	t.Helper()
	f, err := os.Open("../check/stream.jsonl.gz")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	z, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	defer z.Close()
	s := bufio.NewScanner(z)
	s.Buffer(make([]byte, 65536), 4<<20)
	var h Hello
	var observations []Obs
	for s.Scan() {
		var p struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(s.Bytes(), &p); err != nil {
			t.Fatal(err)
		}
		switch p.Type {
		case "hello":
			if err := json.Unmarshal(s.Bytes(), &h); err != nil {
				t.Fatal(err)
			}
		case "obs":
			var o Obs
			if err := json.Unmarshal(s.Bytes(), &o); err != nil {
				t.Fatal(err)
			}
			observations = append(observations, o)
		}
	}
	if err := s.Err(); err != nil {
		t.Fatal(err)
	}
	if len(observations) == 0 {
		t.Fatal("empty recording")
	}
	return h, observations
}

func configuredBrain(t *testing.T, h *Hello) *Brain {
	t.Helper()
	previous := Overrides
	t.Cleanup(func() { Overrides = previous })
	raw, err := os.ReadFile("../cmd/bot/params.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &Overrides); err != nil {
		t.Fatal(err)
	}
	w, err := LoadWorld("../arena")
	if err != nil {
		t.Fatal(err)
	}
	return NewBrain(h, w)
}

func TestRecordedObservationsWithoutRecoveredPanics(t *testing.T) {
	h, observations := fixture(t)
	b := configuredBrain(t, &h)
	for _, o := range observations {
		a := b.Act(&o)
		if a.Tick != o.Tick {
			t.Fatalf("tick mismatch at %d", o.Tick)
		}
		if _, err := json.Marshal(a); err != nil {
			t.Fatal(err)
		}
		if b.Panics != 0 {
			t.Fatalf("controller panic at tick %d", o.Tick)
		}
	}
}

func TestPracticeToEndGhostTransition(t *testing.T) {
	h, observations := fixture(t)
	b := configuredBrain(t, &h)
	o := observations[0]
	o.Mechs, o.Events, o.Sounds, o.Beams = nil, nil, nil, nil
	o.Alive = 16
	o.T, o.Zone.NextRadius = 21, 240
	b.Act(&o)
	if !b.pracOn || b.P.Ghost || b.P.Peek || b.P.LaserRange != 120 {
		t.Fatal("practice combat policy not activated")
	}
	if b.P.Ears {
		t.Fatal("scored revision must keep Ears disabled")
	}
	o.T, o.Zone.NextRadius = 195, 140
	b.Act(&o)
	if !b.endGhostOn || !b.P.Ghost || !b.P.Peek || b.P.Practice {
		t.Fatal("140 m trigger did not restore defensive policy")
	}
	o.T += 0.1
	b.Act(&o)
	if !b.endGhostOn || !b.P.Ghost {
		t.Fatal("defensive policy did not persist")
	}
	if b.Panics != 0 {
		t.Fatal("controller recovered a panic")
	}
}

func TestOtherDeathsDisablePracticeHeuristic(t *testing.T) {
	h, observations := fixture(t)
	b := configuredBrain(t, &h)
	o := observations[0]
	o.Mechs, o.Events = nil, nil
	o.T, o.Alive, o.Zone.NextRadius = 21, 16, 240
	b.Act(&o)
	o.Alive = 15
	for i := 0; i < 5; i++ {
		o.T += 0.1
		b.Act(&o)
	}
	if !b.notPractice || b.pracOn || !b.P.Ghost {
		t.Fatal("FFA heuristic failed")
	}
	if b.Panics != 0 {
		t.Fatal("controller recovered a panic")
	}
}
